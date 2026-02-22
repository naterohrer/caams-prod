import re
from datetime import date
from sqlalchemy.orm import Session
from .. import models


def _natural_sort_key(s: str) -> list:
    """Split string into alternating text/int chunks for natural ordering."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", s)]


def _load_owners(assessment_id: int, db: Session) -> dict[str, dict]:
    """Return a dict of control_id -> {owner, team, evidence_owner}."""
    rows = db.query(models.AssessmentControlOwner).filter(
        models.AssessmentControlOwner.assessment_id == assessment_id
    ).all()
    return {
        r.control_id: {
            "owner": r.owner,
            "team": r.team,
            "evidence_owner": r.evidence_owner,
        }
        for r in rows
    }


def _load_notes(assessment_id: int, db: Session) -> dict[str, dict]:
    """Return a dict of control_id -> {notes, evidence_url, status_override, ...}."""
    rows = db.query(models.AssessmentControlNote).filter(
        models.AssessmentControlNote.assessment_id == assessment_id
    ).all()
    return {
        r.control_id: {
            "notes": r.notes,
            "evidence_url": r.evidence_url,
            "status_override": r.status_override,
            "override_justification": r.override_justification,
            "override_expires": r.override_expires,
        }
        for r in rows
    }


def compute_results(assessment: models.Assessment, db: Session) -> list[dict]:
    """
    For each control in the assessment's framework, determine coverage status
    based on the union of capability tags from all selected tools plus any
    config-based tags (e.g. MFA enforced, logging enabled).
    Manual status overrides (compensating controls) take precedence over computed status.
    """
    # Build per-tool tag sets, including config-derived tags
    tool_tags: dict[int, set[str]] = {}
    for at in assessment.tools:
        tags = {cap.tag for cap in at.tool.capabilities}
        config = at.config or {}
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
        tool_tags[at.tool_id] = tags

    all_tags: set[str] = set()
    for tags in tool_tags.values():
        all_tags |= tags

    controls = (
        db.query(models.Control)
        .filter(models.Control.framework_id == assessment.framework_id)
        .all()
    )
    controls.sort(key=lambda c: _natural_sort_key(c.control_id))

    owners = _load_owners(assessment.id, db)
    notes_map = _load_notes(assessment.id, db)

    results = []
    for control in controls:
        required = set(control.required_tags or [])
        optional = set(control.optional_tags or [])

        satisfied_required = required & all_tags
        satisfied_optional = optional & all_tags
        missing_required = required - all_tags

        contributing_tools = []
        for at in assessment.tools:
            tool_tag_set = tool_tags[at.tool_id]
            if tool_tag_set & (required | optional):
                contributing_tools.append(at.tool.name)

        if not required or satisfied_required == required:
            computed_status = "covered"
        elif satisfied_required or satisfied_optional:
            computed_status = "partial"
        else:
            computed_status = "not_covered"

        ownership = owners.get(control.control_id, {})
        note = notes_map.get(control.control_id, {})

        # Manual override takes precedence when set and not expired
        override = note.get("status_override")
        override_expires = note.get("override_expires")
        status_overridden = False
        if override in ("covered", "partial", "not_covered"):
            if override_expires is None or override_expires >= date.today():
                status = override
                status_overridden = True
            else:
                status = computed_status  # expired override, revert to computed
        else:
            status = computed_status

        results.append(
            {
                "control_id": control.control_id,
                "title": control.title,
                "description": control.description,
                "status": status,
                "status_overridden": status_overridden,
                "satisfied_tags": sorted(satisfied_required | satisfied_optional),
                "missing_tags": sorted(missing_required),
                "contributing_tools": contributing_tools,
                "evidence": control.evidence or [],
                "sub_controls": control.sub_controls or [],
                "owner": ownership.get("owner"),
                "team": ownership.get("team"),
                "evidence_owner": ownership.get("evidence_owner"),
                "notes": note.get("notes"),
                "evidence_url": note.get("evidence_url"),
                "override_justification": note.get("override_justification"),
                "override_expires": override_expires,
            }
        )

    return results


def compute_summary(results: list[dict]) -> dict:
    total = len(results)
    covered = sum(1 for r in results if r["status"] == "covered")
    partial = sum(1 for r in results if r["status"] == "partial")
    not_covered = total - covered - partial
    coverage_pct = round((covered + partial * 0.5) / total * 100, 1) if total else 0.0
    return {
        "total": total,
        "covered": covered,
        "partial": partial,
        "not_covered": not_covered,
        "coverage_pct": coverage_pct,
        "results": results,
    }
