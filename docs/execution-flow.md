# Execution Flow

A narrative walkthrough of one incident, node by node. See
[`state-diagram.md`](state-diagram.md) for the transition diagram and
[`sequence-diagram.md`](sequence-diagram.md) for the cross-layer view.

## 1. Entry: `POST /incident`

`api/routers/incidents.py` validates the request (`schemas/api.
IncidentRequest`) and calls `IncidentController.start_investigation()`,
which builds a fresh `IncidentState` (`graphs/state.create_initial_state`)
and invokes the compiled graph with a new `thread_id`.

## 2. `recall_memory` (entry node)

Before anything else, `MemoryService.recall()` pulls similar past
incidents (Chroma semantic search), the session's conversation summary,
and user preferences (SQLite) into `state["memory"]`. Runs *before*
intent detection so even classification benefits from prior context;
`frequent_fixes` is necessarily empty here since it's looked up per
incident-category, which isn't known yet.

## 3. `intent_detection`

Classifies the report: subsystem category, urgency, keywords, whether it
needs human review. Pure LLM call, no tools.

## 4. `planner`

Decides which evidence-gathering task types are worth running for this
specific incident -- not a fixed list. Also the re-entry point of the
retry cycle (step 8).

## 5. `evidence_gathering` (subgraph, parallel)

`invoke_evidence_subgraph()` hands a copy of state (with accumulator
fields reset -- see that function's docstring for why) to a *separately
compiled* `StateGraph`. Its own entry point (`edges/evidence_routing.
route_to_evidence_tasks`) dispatches one `Send` per planned task, running
that subset of `{log_analysis, metrics_analysis, vector_search,
sql_query, web_search, knowledge_graph}` in parallel. Each branch calls
its agent plus whichever tools are relevant (mocked Kubernetes/Kafka/
Postgres/Redis, the seeded knowledge base, the mock SQL database) and
contributes to `logs`/`metrics`/`retrieved_documents`/`sql_results`/
`tool_results`/`reasoning`/`citations`.

## 6. `merge_results`

Renders the consolidated evidence (raw data + each branch's own
synthesis) once into `state["metadata"]["evidence_bundle"]`, so Root
Cause Analysis, Validator, and Critic all read the same pre-formatted
text instead of each re-deriving it.

## 7. `root_cause_analysis` → `incident_resolution` → `validator` → `critic`

Root Cause Analysis synthesizes the evidence into one causal claim.
Incident Resolution drafts concrete remediation steps. Validator checks
the draft against evidence and produces `confidence_score`. Critic
reviews it independently for soundness (not the same thing -- see
`schemas/critique.py`'s docstring).

## 8. Confidence check (retry cycle)

`edges/confidence_check.route_after_confidence_check` reads
`confidence_score` and `critic_feedback.approve`. Below threshold (and
retries remain) routes to `reflection`, which diagnoses the gap and
routes back to `planner` (step 4) with guidance -- or, once retries are
exhausted or Reflection itself decides more evidence won't help, proceeds
to human approval anyway rather than looping forever.

## 9. `human_approval` (interrupt)

Builds a concise brief (Human Approval Agent) and calls `interrupt()`,
pausing the graph -- checkpointed, resumable from any process. On
resume, `Command(goto=..., update=...)` routes three ways based on the
human's decision: approve/modify-draft to `report_generator`,
modify-plan to `evidence_gathering` (step 5, again -- Edit Plan/Retry/
Skip Tool), or reject to `final_response` directly.

## 10. `report_generator` → `save_memory` → `final_response`

Only on the approved path: generates the durable incident report,
persists it to episodic memory (+ increments fix-usage counts + updates
the conversation summary), then composes the final user-facing answer.
The rejected path skips straight to a deterministic (non-LLM) rejection
message in `final_response`.

## 11. Response

`IncidentController` returns the current state; the API layer projects
it into `IncidentStatusResponse`. If paused, the client (Streamlit UI or
any HTTP client) shows the approval brief and can call `/approve`,
`/reject`, or `/resume`; if complete, it shows `final_answer`.
