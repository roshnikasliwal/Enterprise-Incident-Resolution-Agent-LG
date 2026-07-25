"""Human Approval Agent -- prepares the human-facing brief shown at the
`interrupt()` gate (Phase 8). Does not itself decide approve/reject/modify
-- that decision is `HumanFeedback`, supplied by an actual human via the
API, not this agent's output.
"""

from __future__ import annotations

from incident_agent.agents.base import BaseAgent
from incident_agent.prompts.human_approval import HUMAN_APPROVAL_PROMPT
from incident_agent.schemas.human import ApprovalRequestSummary


class HumanApprovalAgent(BaseAgent[ApprovalRequestSummary]):
    name = "human_approval"
    prompt = HUMAN_APPROVAL_PROMPT
    output_schema = ApprovalRequestSummary
