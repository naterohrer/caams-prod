from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..auth import require_any

router = APIRouter(prefix="/frameworks", tags=["frameworks"])


@router.get("/", response_model=list[schemas.FrameworkOut])
def list_frameworks(db: Session = Depends(get_db), _=Depends(require_any)):
    return db.query(models.Framework).all()


@router.get("/{framework_id}", response_model=schemas.FrameworkOut)
def get_framework(framework_id: int, db: Session = Depends(get_db), _=Depends(require_any)):
    fw = db.query(models.Framework).filter(models.Framework.id == framework_id).first()
    if not fw:
        raise HTTPException(status_code=404, detail="Framework not found")
    return fw


@router.get("/{framework_id}/controls", response_model=list[schemas.ControlOut])
def list_controls(framework_id: int, db: Session = Depends(get_db), _=Depends(require_any)):
    fw = db.query(models.Framework).filter(models.Framework.id == framework_id).first()
    if not fw:
        raise HTTPException(status_code=404, detail="Framework not found")
    return (
        db.query(models.Control)
        .filter(models.Control.framework_id == framework_id)
        .order_by(models.Control.control_id)
        .all()
    )
