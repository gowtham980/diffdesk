"""Pydantic models and domain enums for diffdesk."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReviewSource(str, Enum):
    AGENT = "agent"
    PR = "pr"
    MANUAL = "manual"


class ReviewStatus(str, Enum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    SHIP = "ship"
    CHANGES_REQUESTED = "changes_requested"
    ARCHIVED = "archived"


class RiskLevel(str, Enum):
    LOW = "low"
    MED = "med"
    HIGH = "high"


class FileStatus(str, Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    SKIPPED = "skipped"


class ChecklistStatus(str, Enum):
    TODO = "todo"
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


class FindingSeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MED = "med"
    HIGH = "high"
    CRITICAL = "critical"


class FindingStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    WONTFIX = "wontfix"


# Default AI-slop review checklist categories/labels
DEFAULT_CHECKLIST = [
    ("correctness", "Logic is correct and matches intent"),
    ("security", "No security issues or unsafe patterns"),
    ("tests", "Tests exist / updated for the change"),
    ("naming", "Names are clear and consistent"),
    ("scope", "No unnecessary scope creep"),
    ("secrets", "No secrets, tokens, or credentials"),
    ("errors", "Error handling is intentional"),
    ("performance", "No obvious performance footguns"),
]


# --- API / request models ---


class ReviewCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=240)
    source: ReviewSource = ReviewSource.MANUAL
    risk: RiskLevel = RiskLevel.MED
    summary: str = ""
    diff_text: str = ""


class ReviewUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=240)
    source: Optional[ReviewSource] = None
    status: Optional[ReviewStatus] = None
    risk: Optional[RiskLevel] = None
    summary: Optional[str] = None


class DecisionRequest(BaseModel):
    status: ReviewStatus


class ChecklistUpdate(BaseModel):
    status: ChecklistStatus
    notes: str = ""


class FindingCreate(BaseModel):
    severity: FindingSeverity = FindingSeverity.MED
    file_path: str = ""
    title: str = Field(..., min_length=1, max_length=240)
    body: str = ""


class FindingUpdate(BaseModel):
    severity: Optional[FindingSeverity] = None
    file_path: Optional[str] = None
    title: Optional[str] = Field(None, min_length=1, max_length=240)
    body: Optional[str] = None
    status: Optional[FindingStatus] = None


class TemplateItem(BaseModel):
    category: str
    label: str


class SettingsUpdate(BaseModel):
    checklist_template: list[TemplateItem]


class FileOut(BaseModel):
    id: int
    review_id: int
    path: str
    language: str
    patch: str
    status: FileStatus
    additions: int = 0
    deletions: int = 0


class ChecklistItemOut(BaseModel):
    id: int
    review_id: int
    category: str
    label: str
    status: ChecklistStatus
    notes: str
    sort_order: int


class FindingOut(BaseModel):
    id: int
    review_id: int
    severity: FindingSeverity
    file_path: str
    title: str
    body: str
    status: FindingStatus
    created_at: datetime


class ReviewOut(BaseModel):
    id: int
    title: str
    source: ReviewSource
    status: ReviewStatus
    risk: RiskLevel
    summary: str
    created_at: datetime
    updated_at: datetime
    file_count: int = 0
    finding_count: int = 0
    checklist_done: int = 0
    checklist_total: int = 0


class ReviewDetail(ReviewOut):
    files: list[FileOut] = []
    checklist: list[ChecklistItemOut] = []
    findings: list[FindingOut] = []


class DashboardStats(BaseModel):
    open_count: int
    in_review_count: int
    high_risk_count: int
    ship_count: int
    changes_requested_count: int
    total_count: int
    recent: list[ReviewOut] = []
