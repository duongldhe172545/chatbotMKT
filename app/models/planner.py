"""Planner-first conversation models for Em Linh MKT."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.slots.definitions import SLOT_TO_ALL_FIELDS


DERIVED_PROFILE_FIELDS: set[str] = {
    "province",
    "district",
    "main_category",
    "dealer_type",
    "brand_name_short",
    "initials_full",
    "initial_single",
    "contact_name",
    "contact_role",
    "hotline",
    "slogan_options",
}

PLANNER_ALLOWED_FIELDS: set[str] = {
    field
    for fields in SLOT_TO_ALL_FIELDS.values()
    for field in fields
    if field not in DERIVED_PROFILE_FIELDS
}

PlannerMove = Literal[
    "continue_intake",
    "answer_then_ask",
    "clarify",
    "summarize_confirm",
    "pause_sensitive",
    "close",
]
Confidence = Literal["low", "medium", "high"]


class PlannedFact(BaseModel):
    """One profile fact the planner believes the dealer provided."""

    field: str
    value: Any
    evidence: str = ""
    confidence: Confidence = "medium"

    @field_validator("field")
    @classmethod
    def field_must_be_intake_field(cls, value: str) -> str:
        if value not in PLANNER_ALLOWED_FIELDS:
            raise ValueError(f"Planner field is not allowed: {value}")
        return value


class PlannerResult(BaseModel):
    """Structured output from the planner LLM."""

    move: PlannerMove = "continue_intake"
    facts: list[PlannedFact] = Field(default_factory=list)
    corrections: list[PlannedFact] = Field(default_factory=list)
    next_focus_fields: list[str] = Field(default_factory=list)
    assistant_reply: str = ""
    needs_human_review: bool = False
    risk_flags: list[str] = Field(default_factory=list)

    @field_validator("next_focus_fields")
    @classmethod
    def focus_fields_must_be_intake_fields(cls, value: list[str]) -> list[str]:
        return [field for field in value if field in PLANNER_ALLOWED_FIELDS]


class MissingFieldState(BaseModel):
    """Current checklist state derived from profile, not from hard slot flow."""

    required_missing: list[str] = Field(default_factory=list)
    optional_missing: list[str] = Field(default_factory=list)
    filled_fields: list[str] = Field(default_factory=list)
    next_focus_field: str | None = None
    next_focus_slot: str | None = None
    can_confirm: bool = False

