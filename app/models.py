from sqlalchemy import Column, Integer, String, JSON, ForeignKey, DateTime, Text, Date, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False, unique=True)
    email = Column(String, nullable=True, unique=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="viewer")  # admin | contributor | viewer
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now())


class Framework(Base):
    __tablename__ = "frameworks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    version = Column(String, nullable=False)
    controls = relationship("Control", back_populates="framework")


class Control(Base):
    __tablename__ = "controls"

    id = Column(Integer, primary_key=True, index=True)
    framework_id = Column(Integer, ForeignKey("frameworks.id"), nullable=False)
    control_id = Column(String, nullable=False)  # e.g. "CIS-1"
    title = Column(String, nullable=False)
    description = Column(Text)
    required_tags = Column(JSON, default=list)
    optional_tags = Column(JSON, default=list)
    evidence = Column(JSON, default=list)
    sub_controls = Column(JSON, default=list)  # list of {id, title}
    framework = relationship("Framework", back_populates="controls")


class Tool(Base):
    __tablename__ = "tools"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    category = Column(String, nullable=False)
    capabilities = relationship("ToolCapability", back_populates="tool")


class ToolCapability(Base):
    __tablename__ = "tool_capabilities"

    id = Column(Integer, primary_key=True, index=True)
    tool_id = Column(Integer, ForeignKey("tools.id"), nullable=False)
    tag = Column(String, nullable=False)
    tool = relationship("Tool", back_populates="capabilities")


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    framework_id = Column(Integer, ForeignKey("frameworks.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    framework = relationship("Framework")
    tools = relationship("AssessmentTool", back_populates="assessment")


class AssessmentTool(Base):
    __tablename__ = "assessment_tools"

    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    tool_id = Column(Integer, ForeignKey("tools.id"), nullable=False)
    config = Column(JSON, default=dict)
    assessment = relationship("Assessment", back_populates="tools")
    tool = relationship("Tool")


class AssessmentControlOwner(Base):
    __tablename__ = "assessment_control_owners"

    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    control_id = Column(String, nullable=False)  # e.g. "CIS-1"
    owner = Column(String, nullable=True)
    team = Column(String, nullable=True)
    evidence_owner = Column(String, nullable=True)
    assessment = relationship("Assessment")


class AssessmentControlNote(Base):
    """Per-control notes, evidence links, and manual status overrides."""
    __tablename__ = "assessment_control_notes"

    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    control_id = Column(String, nullable=False)
    notes = Column(Text, nullable=True)
    evidence_url = Column(String, nullable=True)
    # Override values: "covered" | "partial" | "not_covered" | None (auto)
    status_override = Column(String, nullable=True)
    override_justification = Column(Text, nullable=True)
    override_expires = Column(Date, nullable=True)
    assessment = relationship("Assessment")
