"""State reducer functions for `graphs.state.IncidentState`.

LangGraph merges every node's *partial* state update into the running
state using, per key, either the default "last write wins" behavior or
an explicit reducer declared via `Annotated[T, reducer_fn]`.

Two categories of field live in `IncidentState`:

1. "Current snapshot" fields (`intent`, `plan`, `draft_answer`, ...) --
   exactly one node sets these at a time and each new value should
   *replace* the previous one. These need no reducer at all.
2. "Accumulating" fields (`logs`, `tool_results`, `execution_history`,
   ...) -- many nodes (often running in parallel, see the fan-out
   evidence-gathering branch) each contribute entries over the life of
   a run, and a later write must *not* erase earlier ones. These need
   an explicit reducer, otherwise LangGraph either overwrites previous
   contributions or raises `InvalidUpdateError` when two parallel
   branches touch the same key in one super-step.

`list` accumulation uses `operator.add` directly at the call site
(nothing to wrap). The only accumulating shape that isn't a list is
`metadata: dict`, which needs a merge (not concatenation) -- that
reducer lives here.
"""

from __future__ import annotations

from typing import Any


def merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Shallow-merge two metadata dicts, right-hand (newer) keys winning.

    Used as the reducer for `IncidentState["metadata"]` so that, e.g., the
    Log Analysis and Metrics Analysis nodes -- which run in the same
    parallel super-step -- can each stash their own metadata keys
    (`{"log_analysis_duration_ms": ...}` vs `{"metrics_source": ...}`)
    without one clobbering the other.
    """
    if not left:
        return dict(right)
    if not right:
        return dict(left)
    return {**left, **right}
