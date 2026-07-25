"""Reflection Agent structured output.

Runs only on the retry path (confidence below threshold, or the Critic
rejected the draft) -- it diagnoses *why* the attempt fell short and
hands the Planner concrete guidance, which is what turns "retry loop"
into "retry loop that actually converges" instead of repeating the same
mistake.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReflectionOutput(BaseModel):
    what_went_wrong: str = Field(
        description="Diagnosis of why confidence was below threshold or the critic rejected the draft."
    )
    missing_evidence: list[str] = Field(
        default_factory=list, description="Specific gaps in gathered evidence, e.g. 'no metrics for the last 15 minutes'."
    )
    should_replan: bool
    guidance_for_replanner: str = Field(description="Concrete instructions the Planner should follow on the next attempt.")
