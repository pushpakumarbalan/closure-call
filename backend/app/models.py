"""Shared domain models. Every input that drives a decision carries a source and a timestamp."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Posture(str, Enum):
    """Graded closure postures, mirroring OPM operating-status categories."""

    NORMAL = "normal"
    DELAY = "delay"
    EARLY_DISMISSAL = "early_dismissal"
    TELEWORK = "telework"
    CLOSURE = "closure"


POSTURE_RANK = {
    Posture.NORMAL: 0,
    Posture.DELAY: 1,
    Posture.EARLY_DISMISSAL: 2,
    Posture.TELEWORK: 3,
    Posture.CLOSURE: 4,
}

POSTURE_LABEL = {
    Posture.NORMAL: "Open - Normal Operations",
    Posture.DELAY: "Open - Delayed Arrival",
    Posture.EARLY_DISMISSAL: "Open - Early Dismissal",
    Posture.TELEWORK: "Closed to the Public - Unscheduled Leave / Telework",
    Posture.CLOSURE: "Facility Closed",
}


class Signal(BaseModel):
    """One observed input. `value` is machine-comparable, `display` is for humans."""

    key: str
    label: str
    value: Any
    unit: str | None = None
    display: str
    source: str
    source_url: str | None = None
    observed_at: str | None = None
    fetched_at: str = Field(default_factory=now_iso)
    detail: dict[str, Any] = Field(default_factory=dict)


class ThresholdHit(BaseModel):
    rule_id: str
    hazard: str
    signal_key: str
    description: str
    operator: str
    threshold: Any
    observed: Any
    margin_text: str
    posture: Posture
    anchor: str
    anchor_url: str | None = None


class Recommendation(BaseModel):
    facility_id: str
    facility_name: str
    evaluated_at: str
    posture: Posture
    posture_label: str
    hazards: list[str]
    inputs: list[Signal]
    triggered: list[ThresholdHit]
    near_misses: list[ThresholdHit]
    confidence: float
    confidence_reasons: list[str]
    what_would_change: list[str]
    rationale: str
    rationale_source: Literal["agent", "deterministic"]
    agent_trace: list[dict[str, Any]] = Field(default_factory=list)
    drill: bool = False
    drill_note: str | None = None


class Recipient(BaseModel):
    employee_id: str
    name: str
    role: str
    included: bool
    reason: str
    channels: list[str]
    instruction: str


class NotificationPackage(BaseModel):
    posture: Posture
    subject: str
    message: str
    sms: str
    recipients: list[Recipient]
    included_count: int
    excluded_count: int
    channel_summary: dict[str, int]
    generated_at: str = Field(default_factory=now_iso)


class DecisionRecord(BaseModel):
    id: str
    seq: int
    created_at: str
    facility_id: str
    facility_name: str
    recommended_posture: Posture
    decided_posture: Posture
    decided_by: str
    override: bool
    override_reason: str | None
    recommendation: Recommendation
    notification: NotificationPackage | None
    prev_hash: str | None
    hash: str
