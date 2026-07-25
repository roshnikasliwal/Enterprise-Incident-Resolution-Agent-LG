# Build Log: What, Why, LangGraph Concepts, Interview Framing

This project was built incrementally, one phase at a time, each
compiling and passing its own test suite before the next began. This
log is the durable record of what each phase added and why -- the same
explanation given at the end of every phase during development, kept
here instead of only existing in chat history.

## Phase 1 -- Project Scaffolding

**What:** Layered package (`config/controllers/agents/graphs/nodes/
edges/tools/memory/models/prompts/services/schemas/utils/api`), Pydantic
Settings with `env_nested_delimiter="__"`, stdlib-based structured
logging, dependencies pinned and verified installable.

**Why:** Fail-fast config validation; provider failover as a config
change, not code; secrets never rendered in logs/`repr()`.

**LangGraph concepts:** None yet, deliberately -- pure scaffolding for
everything that follows.

**Interview framing:** Config-as-code and dependency verification (this
environment had no C compiler, forcing a real evaluation of package
choices rather than a broken install) are the unglamorous parts that
separate a demo from something someone could actually run.

## Phase 2 -- State, Schemas, Prompts

**What:** `IncidentState` (TypedDict) with `Annotated[list, operator.add]`
reducers on nine accumulating fields and a custom `merge_dicts` reducer
for `metadata`; domain models; one Pydantic structured-output schema per
agent decision point; 17 agent prompts via a shared factory.

**Why:** TypedDict over a Pydantic state model avoids re-validating the
entire state on every parallel branch's partial update; `PlanTask.
depends_on: list[TaskType]` (not `list[task_id]`) avoids an LLM
hallucinating references to server-generated IDs it can't know yet.

**LangGraph concepts:** State schema design, reducers -- proven with a
real compiled `StateGraph`, not just type-hint inspection.

**Interview framing:** Pydantic `Field(description=...)` text becomes
the schema shown to the model during tool-calling structured output --
schema design *is* prompt design.

## Phase 3 -- Tools

**What:** 13 tools (23 `@tool` functions) uniformly wrapped by
`tools/base.run_structured()`; a real Chroma-backed knowledge base
(local ONNX embeddings, no API key needed); a seeded mock SQL database
shared by two tools.

**Why:** Every tool that accepts LLM-controlled input is treated as an
attack surface: AST-walked allowlists instead of `eval`/`exec`
(calculator, Python REPL), hostname resolution + private/loopback/
link-local blocking before connecting (REST API tool -- an SSRF defense
against `169.254.169.254`-style targets), realpath containment checks
(filesystem tool), and independent SQL statement-type enforcement.

**LangGraph concepts:** N/A (LangChain tool layer) -- but this is what
Phase 5's nodes actually call.

**Interview framing:** Every security-relevant tool has a stated threat
model and a test that attempts the actual attack, not just asserts the
mitigation exists.

## Phase 4 -- Agents

**What:** `LLMClientFactory` (Strategy: Anthropic primary, OpenAI/Azure
OpenAI fallback, composed via `with_fallbacks()` + `with_retry()`);
`BaseAgent` (Template Method: `name`/`prompt`/`output_schema` is all a
concrete agent declares); 17 agent classes.

**Why:** Fallback is composed at the *structured-output-runnable* level,
not the bare chat model -- so a Pydantic validation failure on provider A
also triggers provider B, not just a raw transport error.

**LangGraph concepts:** `with_structured_output`, `with_fallbacks`,
`with_retry` composition; `with_config` for LangSmith run naming.

**Interview framing:** Agents are deliberately unaware of `IncidentState`
or LangGraph -- pure `(inputs) -> validated object` units, independently
testable with an injected fake `Runnable`.

## Phase 5 -- Graph

**What:** The full compiled `StateGraph` implementing the workflow --
Send-based dynamic parallel evidence-gathering fan-out, a separately
compiled evidence subgraph, the retry cycle, Command API + `interrupt()`
combined at the human-approval gate, checkpointing (in-memory), and
verified sync/async/streaming invocation.

**Why / found:** Root-caused a real LangGraph bug
(`langchain-ai/langgraph#6290`): embedding a compiled subgraph directly
as a node double-applies the parent's reducers over the subgraph's
entire returned state, silently duplicating accumulator fields that
already had entries before the subgraph ran. Fixed via
`invoke_evidence_subgraph()`, which resets accumulator fields before
invoking and returns only the net-new contributions. Verified with an
instrumented call-counter that the node itself only ran once -- the bug
was in state bookkeeping, not duplicate execution.

**LangGraph concepts:** Every one listed in the requirements --
StateGraph, nodes, edges, conditional edges, parallel branches,
subgraphs, cycles, retry loops, dynamic routing, Command API, Send API,
reducers, checkpointing, resume, streaming, interrupt.

**Interview framing:** The subgraph-reducer bug is the standout story --
a framework-level correctness issue that only surfaces under real
concurrent/cyclic execution, with a fix (reset-then-diff around subgraph
invocation) that generalizes to any shared-schema subgraph with
accumulator fields.

## Phase 6 -- Memory

**What:** Repository pattern over four memory concerns (episodic/
Chroma, preferences/fixes/conversation/SQLite) behind a `MemoryService`
Facade; wired for real into the graph (`recall_memory` as the entry
point, `save_memory_node` genuinely persisting).

**Why:** Recalling before intent detection means even classification
benefits from context, at the cost of `frequent_fixes` being empty on
that first pass (category isn't known yet) -- an accepted, explicit
tradeoff rather than a double-query.

**LangGraph concepts:** N/A directly -- this is business-domain memory,
distinct from "Checkpoint Memory" (LangGraph's own checkpointer, Phase 7).

**Interview framing:** The override-seam pattern
(`override_agent`/`override_memory_service`) is a deliberate, repeated
architectural choice: every external dependency this project can't
easily construct in a test gets the same DI shape, so the whole suite
runs with zero API credentials and zero writes to real project data.

## Phase 7 -- Checkpointing

**What:** `SqliteSaver`-backed checkpointer (Factory + cached singleton);
`ThreadRegistry` (5th memory repository) indexing `(session_id,
thread_id, incident_id)` since LangGraph's checkpointer has no concept
of a user.

**Why:** "Multiple users" isn't something the checkpointer gives you for
free -- it partitions purely by `thread_id`.

**LangGraph concepts:** Checkpointing, resume, multi-thread/multi-user
support -- proven by discarding Python objects entirely between calls
and reconnecting to the same SQLite file, not just object reuse.

**Interview framing:** Recognizing what a framework does *not* give you
(user-scoped persistence) and closing that gap at the application layer
deliberately, rather than assuming it's covered.

## Phase 8 -- Human in the Loop

**What:** `IncidentController` (the transport/graph seam);
`HumanFeedback.modified_plan` (defined in Phase 2, wired now) routes
Edit-Plan/Retry/Skip-Tool through one mechanism; `interrupt_before`/
`interrupt_after` static pause points alongside the existing dynamic
`interrupt()`.

**Why:** Skip Tool doesn't need a separate primitive -- removing a task
from an edited plan before resubmitting it means that task's tool(s)
never run, since the Planner already decides tool usage at task-type
granularity.

**LangGraph concepts:** Static vs. dynamic interrupts (no resume payload
vs. a custom one), `update_state` for direct state mutation independent
of a resume value, `Command` for decision-dependent dynamic routing.

**Interview framing:** A full Skip-Tool run proves a removed task's tool
is *never called*, not just that the plan object looks edited.

## Phase 9 -- FastAPI

**What:** `POST /incident`, `GET /status/{thread_id}`, `GET /history`,
`POST /resume/{thread_id}`, `POST /approve/{thread_id}`, `POST
/reject/{thread_id}`; exception handlers for graceful errors; async
handlers offloading `IncidentController`'s sync graph calls via
`run_in_threadpool`.

**Why / found:** Testing the 404 path surfaced a real bug --
`IncidentController`'s resume-style methods didn't check thread
existence before calling `Command(resume=...)`, producing a confusing
`KeyError` deep in the graph instead of a clean 404. Fixed by validating
via `get_snapshot()` first in every one of those methods.

**LangGraph concepts:** N/A directly -- this is the transport layer atop
everything built so far.

**Interview framing:** `TestClient(app)` without the `with` context
manager (so the lifespan never runs) plus FastAPI's `dependency_overrides`
is the pattern that let API tests exercise real HTTP validation without
ever touching the real checkpoint database.

## Phase 10 -- Docker

**What:** The Streamlit UI (named in the tech stack, not yet built); a
multi-stage `Dockerfile` (non-root, healthcheck); `docker-compose.yml`
(api + ui sharing one image).

**Why:** The UI talks to the API over HTTP, not by importing the graph
in-process -- the same boundary a real deployment has, and it keeps the
UI honest about only using the public API surface.

**LangGraph concepts:** N/A -- deployment packaging.

**Interview framing:** Verified the Dockerfile's inputs (COPY sources,
base image tag currency) since an actual `docker build` wasn't possible
in this sandbox (no daemon permissions) -- explicit about what was and
wasn't verified, rather than claiming untested infrastructure works.

## Phase 11 -- Tests

**What:** Behavioral (not just structural) proof of the fallback/retry
chain; one full incident lifecycle through the real HTTP API end to end;
tests for the four evidence branches that had never actually run through
the graph before.

**Why / found:** The evidence-node coverage gap caught a second real,
previously-undiscovered bug: `Send(node, payload)`'s payload is a
dispatched node's *entire* input state, not merged with the rest of the
graph's state. `vector_search_node` crashed on `state["user_query"]` the
first time it actually ran via `Send` in a test; `log_analysis`/
`metrics_analysis`/`knowledge_graph` nodes were silently degrading
(losing `intent` for target inference) the same way, without a crash to
surface it. Fixed by forwarding shared read-only context in every `Send`
payload from the routing function. Also removed `models/incident.py`
(the `Incident` domain model), built in Phase 2 and never referenced
anywhere -- dead code, not a placeholder worth keeping.

**LangGraph concepts:** A second Send-API gotcha, worth checking for in
any LangGraph project using dynamic dispatch, documented alongside the
Phase 5 subgraph-reducer one.

**Interview framing:** Both real bugs this project found were caught by
deliberately testing paths the "happy path" test suite didn't already
cover (a non-default evidence branch, an unknown-thread error path) --
the lesson generalizes: coverage gaps in a LangGraph project are often
exactly where its concurrency/dispatch primitives haven't been exercised
yet, not where the business logic is.

## Phase 12 -- Documentation

This file, plus [`architecture.md`](architecture.md),
[`sequence-diagram.md`](sequence-diagram.md),
[`state-diagram.md`](state-diagram.md),
[`execution-flow.md`](execution-flow.md),
[`folder-structure.md`](folder-structure.md), and the root
[`README.md`](../README.md).
