"""Critic Agent and Validator Agent structured outputs.

Kept as two distinct schemas even though both "judge" the draft answer:
the Critic checks *quality/soundness* of the reasoning (would a senior
engineer sign off on this?), the Validator checks *correctness against
evidence* (does every claim trace back to something actually gathered?).
Conflating them would hide which failure mode triggered a replan.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CriticIssue(BaseModel):
    issue: str
    severity: Literal["minor", "major", "blocking"]
    suggestion: str


class CriticFeedback(BaseModel):
    issues: list[CriticIssue] = Field(default_factory=list)
    overall_assessment: str
    approve: bool = Field(
        description="True if the draft answer is sound enough to proceed to validation as-is."
    )


class ValidationCheck(BaseModel):
    check_name: str
    passed: bool
    detail: str


class ValidationResult(BaseModel):
    is_valid: bool
    checks: list[ValidationCheck] = Field(default_factory=list)
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Validator's confidence that the draft answer is correct -- feeds the graph's "
        "confidence-threshold routing decision (replan vs. proceed to human approval).",
    )
    notes: str | None = None
