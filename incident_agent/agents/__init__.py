"""Agent layer.

Each agent is a single-responsibility, LLM-backed unit of reasoning (e.g.
Planner, Intent Detection, Root Cause Analysis, Critic). Agents accept and
return typed Pydantic models (see schemas/), never raw strings, and are
independent of LangGraph so they can be unit-tested outside of any graph.
"""
