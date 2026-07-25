"""Graph layer.

LangGraph `StateGraph` definitions. This is where nodes/ and edges/ are
wired together into the incident-resolution workflow, including
subgraphs, parallel fan-out/fan-in branches, retry cycles, and
checkpointer/interrupt configuration. Graphs contain no business logic of
their own -- they compose nodes.
"""
