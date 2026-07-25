# Folder Structure

```
Enterprise-Incident-Resolution-Agent/
├── incident_agent/                  # the application package
│   ├── config/          (2)  Settings (Pydantic Settings), logging setup
│   ├── controllers/     (1)  IncidentController -- transport/graph seam
│   ├── agents/          (19) 17 agents + BaseAgent + registry
│   ├── graphs/          (3)  main_graph, evidence_subgraph, state (IncidentState)
│   ├── nodes/           (24) state-aware glue between graph and agents/tools
│   ├── edges/           (3)  conditional routing functions
│   ├── tools/           (15) 13 LangChain tools + base + registry
│   ├── memory/          (7)  5 repositories + MemoryService facade
│   ├── models/          (5)  domain entities (non-LLM-output)
│   ├── prompts/         (18) 1 factory + 17 per-agent prompt templates
│   ├── services/        (6)  LLM factory, vector store, checkpointer, mock DB, dependency graph
│   ├── schemas/         (13) LLM structured-output + API request/response contracts
│   ├── utils/           (3)  ids, reducers, mock-data helpers
│   └── api/             (2)  FastAPI app factory, dependencies, routers/
├── ui/
│   └── streamlit_app.py       thin HTTP client over the FastAPI backend
├── tests/                     13 test files, 182 tests (unit/agent/tool/graph/integration/UI)
├── docs/                      this directory
├── data/                      local SQLite (checkpoints, memory, mock DB) + Chroma persistence (gitignored)
├── Dockerfile, docker-compose.yml, .dockerignore
├── requirements.txt / requirements.lock.txt
├── pyproject.toml             packaging, pytest/coverage/ruff/mypy config
├── .env.example
├── run_api.py                 `python run_api.py` convenience entry point
└── README.md
```

## Layer responsibilities, in one line each

| Layer | Responsibility |
|---|---|
| `config/` | Typed, env-driven settings; nothing else reads `os.environ` directly |
| `controllers/` | Thin transport-agnostic wrappers around graph operations |
| `agents/` | `(inputs) -> validated Pydantic object`; no LangGraph/state awareness |
| `graphs/` | Compose nodes/edges into `StateGraph`s; no business logic of their own |
| `nodes/` | Translate `IncidentState` <-> agent/tool calls; own the audit trail |
| `edges/` | Pure routing decisions (`state -> next node name` / `list[Send]`) |
| `tools/` | LangChain `@tool`s returning structured JSON (`ToolResult`) |
| `memory/` | Repository pattern over Chroma/SQLite; only ever sees domain models |
| `models/` | Domain entities that flow through state but aren't LLM output |
| `prompts/` | One `ChatPromptTemplate` per agent, built via a shared factory |
| `services/` | Cross-cutting infra: LLM provider selection, vector store, checkpointer |
| `schemas/` | Every LLM structured output and every API request/response shape |
| `utils/` | Stateless helpers with no dependency on any other layer |
| `api/` | FastAPI routers + app factory; talks only to `controllers/` |

Full per-agent, per-tool, and per-node file listing is in the source tree
itself -- naming is 1:1 (`agents/critic.py` <-> `nodes/critic_node.py` <->
`prompts/critic.py` <-> the relevant class in `schemas/`), so there is no
separate index to keep in sync.
