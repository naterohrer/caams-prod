"""
JWT and password utilities — uses only Python standard library + passlib,
to avoid the broken system-level cryptography/cffi bindings on this host.
"""
import os
import hmac
import hashlib
import base64
import json
import time
from typing import Optional
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .database import get_db
from . import models

_raw_secret = os.getenv("CAAMS_SECRET_KEY")
if not _raw_secret:
    raise RuntimeError(
        "CAAMS_SECRET_KEY is not set. "
        "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\" "
        "and add it to /etc/caams.env before starting CAAMS."
    )
SECRET_KEY = _raw_secret.encode()
ACCESS_TOKEN_EXPIRE_SECONDS = 60 * 60 * 8  # 8 hours

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ── Minimal HMAC-SHA256 JWT ────────────────────────────────────────────────────

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))


def create_access_token(user_id: int, role: str, expires_delta: Optional[int] = None) -> str:
    """Return a signed JWT (HMAC-SHA256)."""
    exp = int(time.time()) + (expires_delta or ACCESS_TOKEN_EXPIRE_SECONDS)
    header  = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps({"sub": str(user_id), "role": role, "exp": exp}).encode())
    sig     = _b64url_encode(hmac.new(SECRET_KEY, f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def _decode_token(token: str) -> dict:
    """Decode and verify a JWT. Raise ValueError on any failure."""
    try:
        header_b64, payload_b64, sig = token.split(".")
    except ValueError:
        raise ValueError("Malformed token")
    expected = _b64url_encode(
        hmac.new(SECRET_KEY, f"{header_b64}.{payload_b64}".encode(), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(expected, sig):
        raise ValueError("Invalid signature")
    claims = json.loads(_b64url_decode(payload_b64))
    if claims.get("exp", 0) < time.time():
        raise ValueError("Token expired")
    return claims


# ── Password hashing ───────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── FastAPI dependencies ───────────────────────────────────────────────────────

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Session expired or invalid — please log in again",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        claims = _decode_token(token)
        user_id = int(claims["sub"])
    except Exception:
        raise exc

    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.is_active.is_(True),
    ).first()
    if user is None:
        raise exc
    return user


def require_role(*roles: str):
    """Dependency factory: raise 403 unless user has one of the given roles."""
    def _dep(current_user=Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {' or '.join(roles)}",
            )
        return current_user
    return _dep


require_admin       = require_role("admin")
require_contributor = require_role("admin", "contributor")
require_any         = require_role("admin", "contributor", "viewer")
