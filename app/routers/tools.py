import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..auth import require_any, require_admin

router = APIRouter(prefix="/tools", tags=["tools"])

TOOL_TEMPLATE = [
    {
        "name": "My Custom Tool",
        "category": "EDR",
        "capabilities": ["malware-detection", "endpoint-protection", "behavioral-analytics"]
    },
    {
        "name": "My WAF",
        "category": "WAF",
        "capabilities": ["waf", "web-filtering", "application-security", "IDS-IPS"]
    },
    {
        "name": "My CMDB",
        "category": "CMDB",
        "capabilities": ["cmdb", "asset-inventory", "software-inventory", "configuration-management"]
    },
    {
        "name": "My Ticketing System",
        "category": "ITSM",
        "capabilities": ["itsm", "incident-management", "change-management"]
    },
]


@router.get("/template/download")
def download_template(_=Depends(require_any)):
    """Return a JSON template file the user can fill in with their own tools."""
    return JSONResponse(
        content=TOOL_TEMPLATE,
        headers={"Content-Disposition": 'attachment; filename="caams_tools_template.json"'},
    )


@router.post("/upload")
async def upload_tools(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """
    Upload a JSON file containing an array of tool objects (admin only).
    Each object must have: name (str), category (str), capabilities (list[str]).
    Tools that already exist by name are skipped.
    """
    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="File must be a .json file")

    try:
        raw = await file.read()
        if len(raw) > 1_048_576:  # 1 MB cap
            raise HTTPException(status_code=400, detail="File too large (max 1 MB)")
        tools_data = json.loads(raw)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON — could not parse file")

    if not isinstance(tools_data, list):
        raise HTTPException(status_code=400, detail="JSON must be an array of tool objects")

    added, skipped, errors = [], [], []
    for i, t in enumerate(tools_data):
        if not isinstance(t, dict):
            errors.append(f"Item {i}: not an object")
            continue
        name = t.get("name", "").strip()
        category = t.get("category", "").strip()
        capabilities = t.get("capabilities", [])
        if not name:
            errors.append(f"Item {i}: missing 'name'")
            continue
        if not category:
            errors.append(f"Item {i} ({name}): missing 'category'")
            continue
        if not isinstance(capabilities, list) or not all(isinstance(c, str) for c in capabilities):
            errors.append(f"Item {i} ({name}): 'capabilities' must be a list of strings")
            continue

        existing = db.query(models.Tool).filter(models.Tool.name == name).first()
        if existing:
            skipped.append(name)
            continue

        db_tool = models.Tool(name=name, category=category)
        db.add(db_tool)
        db.flush()
        for tag in capabilities:
            db.add(models.ToolCapability(tool_id=db_tool.id, tag=tag.strip()))
        added.append(name)

    db.commit()
    return {
        "added": len(added),
        "skipped": len(skipped),
        "errors": errors,
        "added_tools": added,
        "skipped_tools": skipped,
    }


@router.get("/", response_model=list[schemas.ToolOut])
def list_tools(db: Session = Depends(get_db), _=Depends(require_any)):
    return db.query(models.Tool).order_by(models.Tool.category, models.Tool.name).all()


@router.post("/", response_model=schemas.ToolOut, status_code=201)
def create_tool(tool: schemas.ToolCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    existing = db.query(models.Tool).filter(models.Tool.name == tool.name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Tool '{tool.name}' already exists")
    db_tool = models.Tool(name=tool.name, category=tool.category)
    db.add(db_tool)
    db.flush()
    for tag in tool.capabilities:
        db.add(models.ToolCapability(tool_id=db_tool.id, tag=tag))
    db.commit()
    db.refresh(db_tool)
    return db_tool


@router.get("/{tool_id}", response_model=schemas.ToolOut)
def get_tool(tool_id: int, db: Session = Depends(get_db), _=Depends(require_any)):
    tool = db.query(models.Tool).filter(models.Tool.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


@router.delete("/{tool_id}", status_code=204)
def delete_tool(tool_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    tool = db.query(models.Tool).filter(models.Tool.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    db.query(models.ToolCapability).filter(models.ToolCapability.tool_id == tool_id).delete()
    db.delete(tool)
    db.commit()
