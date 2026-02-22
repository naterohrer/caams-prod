import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..limiter import limiter
from ..auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_admin, ACCESS_TOKEN_EXPIRE_SECONDS,
)

_log = logging.getLogger("caams.app")

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/setup-needed")
def setup_needed(db: Session = Depends(get_db)):
    """Public: returns whether the initial admin account still needs to be created."""
    return {"needed": db.query(models.User).count() == 0}


@router.post("/setup", status_code=201)
def initial_setup(request: Request, data: schemas.UserCreate, db: Session = Depends(get_db)):
    """Create the first admin. Fails if any user already exists."""
    if db.query(models.User).count() > 0:
        raise HTTPException(status_code=400, detail="Setup already complete — please log in")
    user = models.User(
        username=data.username.strip(),
        email=(data.email or "").strip() or None,
        hashed_password=hash_password(data.password),
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _log.info(
        "SETUP | admin account created | user=%s | ip=%s",
        user.username,
        request.client.host if request.client else "unknown",
    )
    token = create_access_token(user.id, user.role, ACCESS_TOKEN_EXPIRE_SECONDS)
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user.username,
        "role": user.role,
    }


@router.post("/login")
@limiter.limit("10/minute")
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else "unknown"
    user = db.query(models.User).filter(
        models.User.username == form.username,
        models.User.is_active.is_(True),
    ).first()
    if not user or not verify_password(form.password, user.hashed_password):
        _log.warning("LOGIN failed | username=%s | ip=%s", form.username, ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    _log.info("LOGIN success | user=%s | role=%s | ip=%s", user.username, user.role, ip)
    token = create_access_token(user.id, user.role, ACCESS_TOKEN_EXPIRE_SECONDS)
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user.username,
        "role": user.role,
    }


@router.get("/me", response_model=schemas.UserOut)
def me(current_user=Depends(get_current_user)):
    return current_user


# ── User management (admin only) ──────────────────────────────────────────────

@router.get("/users", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db), _=Depends(require_admin)):
    return db.query(models.User).order_by(models.User.created_at).all()


@router.post("/users", response_model=schemas.UserOut, status_code=201)
def create_user(
    data: schemas.UserCreate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),   # noqa: kept as _ since log uses user.username below
):
    if data.role not in ("admin", "contributor", "viewer"):
        raise HTTPException(status_code=422, detail="role must be admin, contributor, or viewer")
    if db.query(models.User).filter(models.User.username == data.username).first():
        raise HTTPException(status_code=409, detail=f"Username '{data.username}' already exists")
    user = models.User(
        username=data.username.strip(),
        email=(data.email or "").strip() or None,
        hashed_password=hash_password(data.password),
        role=data.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _log.info("USER created | user=%s | role=%s", user.username, user.role)
    return user


@router.patch("/users/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    data: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if data.role is not None:
        if data.role not in ("admin", "contributor", "viewer"):
            raise HTTPException(status_code=422, detail="role must be admin, contributor, or viewer")
        if user.role == "admin" and data.role != "admin":
            admins_left = db.query(models.User).filter(
                models.User.role == "admin", models.User.is_active.is_(True)
            ).count()
            if admins_left <= 1:
                raise HTTPException(status_code=400, detail="Cannot demote the last active admin")
        user.role = data.role

    if data.password:
        user.hashed_password = hash_password(data.password)

    if data.is_active is not None:
        if user.id == current_user.id and not data.is_active:
            raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
        if not data.is_active and user.role == "admin" and user.is_active:
            admins_left = db.query(models.User).filter(
                models.User.role == "admin", models.User.is_active.is_(True)
            ).count()
            if admins_left <= 1:
                raise HTTPException(status_code=400, detail="Cannot deactivate the last active admin")
        user.is_active = data.is_active

    db.commit()
    db.refresh(user)
    _log.info(
        "USER updated | user=%s | by=%s",
        user.username, current_user.username,
    )
    return user


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    if user.role == "admin":
        admins_left = db.query(models.User).filter(
            models.User.role == "admin", models.User.is_active.is_(True)
        ).count()
        if admins_left <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last active admin")
    _log.warning(
        "USER deleted | user=%s | by=%s",
        user.username, current_user.username,
    )
    db.delete(user)
    db.commit()
