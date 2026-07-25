"""Planner Agent structured output.

Design note on `PlanTask.depends_on`: it is typed as `list[TaskType]`
(referencing the fixed evidence-gathering *capabilities*), not
`list[task_id]`. `task_id` is server-generated (`default_factory`) after
the LLM call returns, so the model has no way to know another task's ID
while composing the plan -- asking it to reference IDs would only invite
hallucinated/mismatched references. `TaskType` is a small closed enum
the model already has to choose from for `task_type`, so referencing it
for dependencies is both expressible and unambiguous.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from incident_agent.models.enums import TaskStatus, TaskType
from incident_agent.utils.ids import generate_task_id


class PlanTask(BaseModel):
    task_id: str = Field(default_factory=generate_task_id)
    task_type: TaskType = Field(description="Which evidence-gathering capability this task invokes.")
    description: str = Field(description="What this task investigates and why, in one sentence.")
    depends_on: list[TaskType] = Field(
        default_factory=list,
        description="Other task types that must complete first. Leave empty for tasks that "
        "can run immediately in the parallel evidence-gathering fan-out.",
    )
    status: TaskStatus = TaskStatus.PENDING


class ExecutionPlan(BaseModel):
    """The Planner Agent's structured output -- fans out into the parallel
    evidence-gathering branch (Send API, see graphs/) after this is produced.
    """

    plan_id: str = Field(default_factory=generate_task_id)
    incident_summary: str = Field(
        description="Planner's restatement of the problem, used to keep every downstream agent aligned."
    )
    tasks: list[PlanTask] = Field(min_length=1, description="Investigation tasks the graph will execute.")
    rationale: str = Field(description="Why these specific tasks were chosen over the alternatives.")
