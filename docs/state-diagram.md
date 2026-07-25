# State Diagram

The compiled graph's node transitions (see
[`../incident_agent/graphs/main_graph.py`](../incident_agent/graphs/main_graph.py)).
`evidence_gathering` is itself a separately-compiled subgraph with its
own internal Send-based fan-out -- see
[`sequence-diagram.md`](sequence-diagram.md) for that detail expanded.

```mermaid
stateDiagram-v2
    [*] --> recall_memory

    recall_memory --> intent_detection
    intent_detection --> planner
    planner --> evidence_gathering: Send() fan-out,\nsized to the plan
    evidence_gathering --> merge_results
    merge_results --> root_cause_analysis
    root_cause_analysis --> incident_resolution
    incident_resolution --> validator
    validator --> critic

    critic --> reflection: confidence < threshold\nor critic rejects,\nretries remain
    critic --> human_approval: confidence OK\nand critic approves,\nor retries exhausted

    reflection --> planner: should_replan=true,\nretries remain
    reflection --> human_approval: should_replan=false,\nor retries exhausted

    state human_approval {
        [*] --> interrupt_paused: interrupt() pauses here\n(dynamic, carries the\napproval brief payload)
        interrupt_paused --> [*]: Command(resume=HumanFeedback)
    }

    human_approval --> report_generator: APPROVED / AUTO_APPROVED /\nMODIFIED+draft_answer
    human_approval --> evidence_gathering: MODIFIED+modified_plan\n(Edit Plan / Retry / Skip Tool,\nretry_count += 1)
    human_approval --> final_response: REJECTED

    report_generator --> save_memory
    save_memory --> final_response
    final_response --> [*]
```

## Retry cycle termination

`retry_count` (state) and `settings.max_replan_attempts` bound the
`critic -> reflection -> planner -> ... -> critic` cycle -- see
[`../incident_agent/edges/confidence_check.py`](../incident_agent/edges/confidence_check.py)
and
[`../incident_agent/edges/reflection_routing.py`](../incident_agent/edges/reflection_routing.py).
Once exhausted, the run always proceeds to `human_approval` regardless
of confidence -- a persistently low-confidence incident still reaches a
human decision point rather than looping forever or silently completing.

## Static interrupts (orthogonal to the diagram above)

`build_incident_graph(interrupt_before=[...], interrupt_after=[...])`
can pause unconditionally before/after any named node, independent of
`human_approval`'s dynamic `interrupt()`. These don't appear in the
diagram above because they're an opt-in compile-time configuration, not
part of the default topology -- see
[`../tests/test_phase8_human_in_the_loop.py`](../tests/test_phase8_human_in_the_loop.py)'s
`TestStaticInterrupts` for both in action.
