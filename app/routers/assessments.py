import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..engine.mapper import compute_results, compute_summary
from ..auth import require_any, require_contributor, require_admin

_log = logging.getLogger("caams.app")

router = APIRouter(prefix="/assessments", tags=["assessments"])


# ── History (must be before /{assessment_id}) ─────────────────────────────────

@router.get("/history", response_model=list[schemas.AssessmentHistoryItem])
def assessment_history(db: Session = Depends(get_db), _=Depends(require_any)):
    """Return all past assessments with their computed coverage summary."""
    assessments = (
        db.query(models.Assessment)
        .order_by(models.Assessment.created_at.desc())
        .all()
    )
    items = []
    for a in assessments:
        summary = compute_summary(compute_results(a, db))
        items.append(schemas.AssessmentHistoryItem(
            id=a.id,
            name=a.name,
            framework=a.framework.name,
            created_at=a.created_at,
            total=summary["total"],
            covered=summary["covered"],
            partial=summary["partial"],
            not_covered=summary["not_covered"],
            coverage_pct=summary["coverage_pct"],
        ))
    return items


# ── Create / List / Get / Delete ──────────────────────────────────────────────

@router.post("/", response_model=schemas.AssessmentOut, status_code=201)
def create_assessment(
    assessment: schemas.AssessmentCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_contributor),
):
    framework = db.query(models.Framework).filter(
        models.Framework.id == assessment.framework_id
    ).first()
    if not framework:
        raise HTTPException(status_code=404, detail="Framework not found")

    db_assessment = models.Assessment(
        name=assessment.name,
        framework_id=assessment.framework_id,
    )
    db.add(db_assessment)
    db.flush()

    for tool_input in assessment.tools:
        tool = db.query(models.Tool).filter(models.Tool.id == tool_input.tool_id).first()
        if not tool:
            raise HTTPException(
                status_code=404, detail=f"Tool id={tool_input.tool_id} not found"
            )
        db.add(
            models.AssessmentTool(
                assessment_id=db_assessment.id,
                tool_id=tool_input.tool_id,
                config=tool_input.config or {},
            )
        )

    db.commit()
    db.refresh(db_assessment)
    _log.info(
        "ASSESSMENT created | id=%d | name=%s | framework=%s | user=%s",
        db_assessment.id,
        db_assessment.name,
        db_assessment.framework.name,
        current_user.username,
    )
    return db_assessment


@router.get("/", response_model=list[schemas.AssessmentOut])
def list_assessments(db: Session = Depends(get_db), _=Depends(require_any)):
    return db.query(models.Assessment).order_by(models.Assessment.created_at.desc()).all()


@router.get("/{assessment_id}", response_model=schemas.AssessmentOut)
def get_assessment(assessment_id: int, db: Session = Depends(get_db), _=Depends(require_any)):
    assessment = db.query(models.Assessment).filter(
        models.Assessment.id == assessment_id
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return assessment


@router.get("/{assessment_id}/results", response_model=schemas.CoverageSummary)
def get_results(assessment_id: int, db: Session = Depends(get_db), _=Depends(require_any)):
    assessment = db.query(models.Assessment).filter(
        models.Assessment.id == assessment_id
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    results = compute_results(assessment, db)
    return compute_summary(results)


@router.delete("/{assessment_id}", status_code=204)
def delete_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(require_admin),
):
    assessment = db.query(models.Assessment).filter(
        models.Assessment.id == assessment_id
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    _log.warning(
        "ASSESSMENT deleted | id=%d | name=%s | by=%s",
        assessment.id, assessment.name, current_admin.username,
    )
    db.query(models.AssessmentTool).filter(
        models.AssessmentTool.assessment_id == assessment_id
    ).delete()
    db.query(models.AssessmentControlOwner).filter(
        models.AssessmentControlOwner.assessment_id == assessment_id
    ).delete()
    db.query(models.AssessmentControlNote).filter(
        models.AssessmentControlNote.assessment_id == assessment_id
    ).delete()
    db.delete(assessment)
    db.commit()


# ── Ownership ─────────────────────────────────────────────────────────────────

@router.patch(
    "/{assessment_id}/controls/{control_id}/ownership",
    response_model=schemas.OwnershipUpdate,
)
def update_ownership(
    assessment_id: int,
    control_id: str,
    data: schemas.OwnershipUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_contributor),
):
    assessment = db.query(models.Assessment).filter(
        models.Assessment.id == assessment_id
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    row = db.query(models.AssessmentControlOwner).filter(
        models.AssessmentControlOwner.assessment_id == assessment_id,
        models.AssessmentControlOwner.control_id == control_id,
    ).first()

    if row is None:
        row = models.AssessmentControlOwner(
            assessment_id=assessment_id,
            control_id=control_id,
        )
        db.add(row)

    if data.owner is not None:
        row.owner = data.owner or None
    if data.team is not None:
        row.team = data.team or None
    if data.evidence_owner is not None:
        row.evidence_owner = data.evidence_owner or None

    db.commit()
    db.refresh(row)
    return schemas.OwnershipUpdate(
        owner=row.owner,
        team=row.team,
        evidence_owner=row.evidence_owner,
    )


# ── Per-control notes, evidence URL, and status overrides ─────────────────────

@router.patch(
    "/{assessment_id}/controls/{control_id}/notes",
    response_model=schemas.ControlNoteOut,
)
def upsert_control_note(
    assessment_id: int,
    control_id: str,
    data: schemas.ControlNoteUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_contributor),
):
    assessment = db.query(models.Assessment).filter(
        models.Assessment.id == assessment_id
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    row = db.query(models.AssessmentControlNote).filter(
        models.AssessmentControlNote.assessment_id == assessment_id,
        models.AssessmentControlNote.control_id == control_id,
    ).first()

    if row is None:
        row = models.AssessmentControlNote(
            assessment_id=assessment_id,
            control_id=control_id,
        )
        db.add(row)

    if data.notes is not None:
        row.notes = data.notes or None
    if data.evidence_url is not None:
        row.evidence_url = data.evidence_url or None
    if data.status_override is not None:
        valid = {"covered", "partial", "not_covered", ""}
        if data.status_override not in valid:
            raise HTTPException(
                status_code=422,
                detail="status_override must be 'covered', 'partial', 'not_covered', or ''",
            )
        if data.status_override != (row.status_override or ""):
            _log.warning(
                "OVERRIDE | assessment=%d | control=%s | status=%s | expires=%s | by=%s",
                assessment_id,
                control_id,
                data.status_override or "cleared",
                data.override_expires or "none",
                current_user.username,
            )
        row.status_override = data.status_override or None
    if data.override_justification is not None:
        row.override_justification = data.override_justification or None
    if data.override_expires is not None:
        row.override_expires = data.override_expires

    db.commit()
    db.refresh(row)
    return schemas.ControlNoteOut(
        control_id=row.control_id,
        notes=row.notes,
        evidence_url=row.evidence_url,
        status_override=row.status_override,
        override_justification=row.override_justification,
        override_expires=row.override_expires,
    )


@router.get(
    "/{assessment_id}/controls/{control_id}/notes",
    response_model=schemas.ControlNoteOut,
)
def get_control_note(
    assessment_id: int,
    control_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_any),
):
    row = db.query(models.AssessmentControlNote).filter(
        models.AssessmentControlNote.assessment_id == assessment_id,
        models.AssessmentControlNote.control_id == control_id,
    ).first()

    if row is None:
        return schemas.ControlNoteOut(control_id=control_id)

    return schemas.ControlNoteOut(
        control_id=row.control_id,
        notes=row.notes,
        evidence_url=row.evidence_url,
        status_override=row.status_override,
        override_justification=row.override_justification,
        override_expires=row.override_expires,
    )


# ── Clone assessment ──────────────────────────────────────────────────────────

@router.post("/{assessment_id}/clone", response_model=schemas.AssessmentOut, status_code=201)
def clone_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_contributor),
):
    src = db.query(models.Assessment).filter(
        models.Assessment.id == assessment_id
    ).first()
    if not src:
        raise HTTPException(status_code=404, detail="Assessment not found")

    clone = models.Assessment(
        name=f"{src.name} (copy)",
        framework_id=src.framework_id,
    )
    db.add(clone)
    db.flush()

    for at in src.tools:
        db.add(models.AssessmentTool(
            assessment_id=clone.id,
            tool_id=at.tool_id,
            config=dict(at.config or {}),
        ))

    for r in db.query(models.AssessmentControlOwner).filter(
        models.AssessmentControlOwner.assessment_id == assessment_id
    ).all():
        db.add(models.AssessmentControlOwner(
            assessment_id=clone.id,
            control_id=r.control_id,
            owner=r.owner,
            team=r.team,
            evidence_owner=r.evidence_owner,
        ))

    for r in db.query(models.AssessmentControlNote).filter(
        models.AssessmentControlNote.assessment_id == assessment_id
    ).all():
        db.add(models.AssessmentControlNote(
            assessment_id=clone.id,
            control_id=r.control_id,
            notes=r.notes,
            evidence_url=r.evidence_url,
            status_override=r.status_override,
            override_justification=r.override_justification,
            override_expires=r.override_expires,
        ))

    db.commit()
    db.refresh(clone)
    return clone


# ── Capability-gap recommendations ───────────────────────────────────────────

@router.get(
    "/{assessment_id}/recommendations",
    response_model=list[schemas.CapabilityGap],
)
def get_recommendations(
    assessment_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_any),
):
    """
    Return capability gaps: required tags not yet covered by the selected tools,
    ranked by how many controls depend on each missing capability.
    No vendor or product names are included in the response.
    """
    assessment = db.query(models.Assessment).filter(
        models.Assessment.id == assessment_id
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    # Build the set of capability tags already covered by selected tools
    covered_tags: set[str] = set()
    for at in assessment.tools:
        config = at.config or {}
        tags = {cap.tag for cap in at.tool.capabilities}
        if config.get("mfa_enforced"):
            tags.add("MFA")
        if config.get("logging_enabled"):
            tags.add("log-management")
        if config.get("retention_days", 0) >= 90:
            tags.add("log-retention")
        if config.get("backup_testing"):
            tags.add("backup-testing")
        if config.get("hardening_applied"):
            tags.add("hardening")
        covered_tags |= tags

    # For each control, find which required tags are still missing
    controls = (
        db.query(models.Control)
        .filter(models.Control.framework_id == assessment.framework_id)
        .all()
    )

    # capability -> list of control IDs that need it
    gaps: dict[str, list[str]] = {}
    for ctrl in controls:
        for tag in set(ctrl.required_tags or []) - covered_tags:
            gaps.setdefault(tag, []).append(ctrl.control_id)

    if not gaps:
        return []

    return sorted(
        [
            schemas.CapabilityGap(
                capability=tag,
                controls_count=len(ctrl_ids),
                controls_detail=sorted(ctrl_ids),
            )
            for tag, ctrl_ids in gaps.items()
        ],
        key=lambda g: g.controls_count,
        reverse=True,
    )[:10]
