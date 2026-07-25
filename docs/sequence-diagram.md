# Sequence Diagram

A full incident lifecycle: creation, the automated evidence-gathering
fan-out, the retry cycle, and human approval -- across the transport,
orchestration, and reasoning layers.

```mermaid
sequenceDiagram
    actor User
    participant UI as Streamlit UI
    participant API as FastAPI
    participant Ctrl as IncidentController
    participant Graph as Main Graph
    participant Sub as Evidence Subgraph
    participant Mem as MemoryService
    participant LLM as LLM Provider (via LLMClientFactory)

    User->>UI: "My checkout-api pods keep restarting"
    UI->>API: POST /incident
    API->>Ctrl: start_investigation(user_query)
    Ctrl->>Graph: invoke(IncidentState, thread_id)

    Graph->>Mem: recall(user_query, session_id)
    Mem-->>Graph: MemoryContext (similar incidents, prefs, fixes)
    Graph->>LLM: Intent Detection Agent
    LLM-->>Graph: IntentClassification
    Graph->>LLM: Planner Agent
    LLM-->>Graph: ExecutionPlan (which task types to run)

    Graph->>Sub: invoke_evidence_subgraph(state)
    Note over Sub: Send() dispatches one task<br/>per planned task type, in parallel
    par Log Analysis
        Sub->>LLM: Log Analysis Agent
    and Metrics Analysis
        Sub->>LLM: Metrics Analysis Agent
    end
    Sub-->>Graph: net-new evidence only<br/>(logs, metrics, reasoning, ...)

    Graph->>Graph: merge_results (build evidence_bundle)
    Graph->>LLM: Root Cause Analysis Agent
    Graph->>LLM: Incident Resolution Agent
    Graph->>LLM: Validator Agent
    Graph->>LLM: Critic Agent

    alt confidence < threshold, retries remain
        Graph->>LLM: Reflection Agent
        Graph->>Graph: loop back to Planner
        Note over Graph,Sub: evidence gathering + synthesis run again
    end

    Graph->>LLM: Human Approval Agent (builds the brief)
    Graph->>Graph: interrupt() -- pauses, checkpointed
    Graph-->>Ctrl: state + __interrupt__ payload
    Ctrl-->>API: IncidentStatusResponse (is_paused=true)
    API-->>UI: 201 Created
    UI-->>User: Show approval brief

    User->>UI: Approve
    UI->>API: POST /approve/{thread_id}
    API->>Ctrl: approve(thread_id, comments)
    Ctrl->>Graph: invoke(Command(resume=HumanFeedback), thread_id)
    Graph->>Graph: Command(goto="report_generator")
    Graph->>LLM: Report Generator Agent
    Graph->>Mem: persist_incident, record_fix_usage, update_conversation
    Graph->>LLM: Final Response Agent
    Graph-->>Ctrl: final state (final_answer set)
    Ctrl-->>API: IncidentStatusResponse (is_paused=false)
    API-->>UI: 200 OK
    UI-->>User: Show final answer + report
```
