# Enterprise Incident Resolution Agent

A production-grade, multi-agent **LangGraph** system that acts as an AI
Support Engineer: it investigates infrastructure incidents (Kubernetes,
Kafka, PostgreSQL, Redis, HTTP services) end-to-end -- intent detection,
planning, parallel evidence gathering, root-cause analysis, validation,
critique, human-in-the-loop approval, and incident-report generation --
with full checkpointing, memory, and observability.

> **Status:** built incrementally, phase by phase. See [`docs/PHASES.md`](docs/PHASES.md)
> (added in Phase 12) for the full build log. Current phase: **Phase 1 --
> Project Scaffolding** (complete).

## Tech stack

Python 3.14 · LangGraph · LangChain · Anthropic (primary) with OpenAI /
Azure OpenAI fallback · Pydantic v2 · FastAPI · Streamlit · SQLite
checkpointer · Chroma · Docker · LangSmith · Pytest.

## Project layout

```
incident_agent/
    config/        # Pydantic Settings, logging setup
    controllers/    # Orchestration between API and graphs
    agents/         # Single-responsibility LLM agents (structured output)
    graphs/          # LangGraph StateGraph definitions
    nodes/           # Node callables wrapping agents/tools
    edges/           # Conditional routing functions
    tools/           # LangChain tools (mocked infra, RAG, SQL, REPL, ...)
    memory/          # Conversation / long-term / semantic / episodic memory
    models/          # Domain entities (Incident, Plan, ExecutionStep, ...)
    prompts/         # Versioned prompt templates per agent
    services/        # LLM client factory, vector store, DB session mgmt
    schemas/         # LLM structured-output + API request/response models
    utils/           # Stateless helpers (retries, id gen, JSON repair)
    api/             # FastAPI routers + app factory
tests/               # Unit / agent / tool / graph / integration tests
docs/                # Architecture, sequence, state diagrams
ui/                  # Streamlit front-end (added in a later phase)
docker/              # Dockerfile, docker-compose (added in a later phase)
data/                # Local SQLite checkpoints, memory DB, Chroma store
```

## Getting started

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

cp .env.example .env   # then fill in ANTHROPIC__API_KEY at minimum

pytest -m unit
```

`requirements.lock.txt` records the exact versions resolved and verified
against this Python interpreter -- use it (`pip install -r
requirements.lock.txt`) when you want a fully reproducible environment
rather than the loosely-pinned `requirements.txt`.

## Configuration

All configuration is centralized in `incident_agent/config/settings.py`
via `pydantic-settings`, using `env_nested_delimiter="__"` so a single
`.env` populates a settings tree, e.g. `LLM__PRIMARY_PROVIDER=openai`
switches the primary model provider with no code change. See
`.env.example` for every supported variable.
