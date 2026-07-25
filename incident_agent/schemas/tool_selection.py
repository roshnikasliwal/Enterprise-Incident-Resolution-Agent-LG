"""Tool Selection Agent structured output.

Separated from the evidence-gathering agents' own outputs because tool
selection is a distinct decision -- *which* tools a task should invoke --
that happens before those agents run their tools, not a byproduct of
running them.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ToolSelectionDecision(BaseModel):
    selected_tools: list[str] = Field(
        description="Names of tools (matching a tool's `.name`) to invoke for the current task."
    )
    rationale: str
    skip_tools: list[str] = Field(
        default_factory=list, description="Tools explicitly considered and rejected for this task."
    )
