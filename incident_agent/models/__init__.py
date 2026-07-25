"""Domain model layer.

Plain Pydantic domain entities (Incident, ExecutionStep, Plan, Citation,
etc.) that represent business concepts independent of any LLM call or API
transport. Distinct from schemas/, which holds LLM structured-output and
API request/response contracts.
"""
