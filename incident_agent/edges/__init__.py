"""Edge layer.

Conditional-routing callables used by `add_conditional_edges`. Each
function inspects the current state and returns the name of the next
node/branch (or a `Send`/`Command` object), keeping routing decisions out
of node implementations so they can be tested in isolation.
"""
