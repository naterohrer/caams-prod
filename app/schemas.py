#define 'table' headers for db items
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, date
from typing import Optional


class FrameworkOut(BaseModel):
    id: int
    name: str
    version: str

    model_config = {"from_attributes": True}


class ControlOut(BaseModel):
    id: int
    control_id: str
    title: str
    description: Optional[str] = None
    required_tags: list[str] = []
    optional_tags: list[str] = []
    evidence: list[str] = []

    model_config = {"from_attributes": True}


class ToolCreate(BaseModel):
    name: str = Field(max_length=128)
    category: str = Field(max_length=64)
    capabilities: list[str]


class ToolOut(BaseModel):
    id: int
    name: str
    category: str
    capabilities: list[str] = []

    model_config = {"from_attributes": True}

    @field_validator("capabilities", mode="before")
    @classmethod
    def extract_tags(cls, v):
        if v and hasattr(v[0], "tag"):
            return [cap.tag for cap in v]
        return v


class AssessmentToolInput(BaseModel):
    tool_id: int
    config: Optional[dict] = {}


class AssessmentCreate(BaseModel):
    name: str = Field(max_length=128)
    framework_id: int
    tools: list[AssessmentToolInput]


class AssessmentToolOut(BaseModel):
    tool_id: int
    config: dict = {}

    model_config = {"from_attributes": True}


class AssessmentOut(BaseModel):
    id: int
    name: str
    framework_id: int
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class OwnershipUpdate(BaseModel):
    owner: Optional[str] = Field(default=None, max_length=128)
    team: Optional[str] = Field(default=None, max_length=128)
    evidence_owner: Optional[str] = Field(default=None, max_length=128)


class ControlNoteUpdate(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=4000)
    evidence_url: Optional[str] = Field(default=None, max_length=2048)
    status_override: Optional[str] = None   # "covered" | "partial" | "not_covered" | "" to clear
    override_justification: Optional[str] = Field(default=None, max_length=2000)
    override_expires: Optional[date] = None


class ControlNoteOut(BaseModel):
    control_id: str
    notes: Optional[str] = None
    evidence_url: Optional[str] = None
    status_override: Optional[str] = None
    override_justification: Optional[str] = None
    override_expires: Optional[date] = None

    model_config = {"from_attributes": True}


class ControlResult(BaseModel):
    control_id: str
    title: str
    description: Optional[str] = None
    status: str  # "covered" | "partial" | "not_covered"
    status_overridden: bool = False
    satisfied_tags: list[str]
    missing_tags: list[str]
    contributing_tools: list[str]
    evidence: list[str]
    sub_controls: list[dict] = []  # list of {id, title}
    owner: Optional[str] = None
    team: Optional[str] = None
    evidence_owner: Optional[str] = None
    notes: Optional[str] = None
    evidence_url: Optional[str] = None
    override_justification: Optional[str] = None
    override_expires: Optional[date] = None


class CapabilityGap(BaseModel):
    capability: str          # missing capability tag, e.g. "EDR", "MFA"
    controls_count: int      # number of controls that require this capability
    controls_detail: list[str]  # the control IDs affected


class CoverageSummary(BaseModel):
    total: int
    covered: int
    partial: int
    not_covered: int
    coverage_pct: float
    results: list[ControlResult]


# ── Auth / User schemas ───────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str = Field(max_length=64)
    email: Optional[str] = Field(default=None, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    role: Optional[str] = "viewer"  # admin | contributor | viewer


class UserUpdate(BaseModel):
    role: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    is_active: Optional[bool] = None


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── History schema ────────────────────────────────────────────────────────────

class AssessmentHistoryItem(BaseModel):
    id: int
    name: str
    framework: str
    created_at: Optional[datetime] = None
    total: int
    covered: int
    partial: int
    not_covered: int
    coverage_pct: float
