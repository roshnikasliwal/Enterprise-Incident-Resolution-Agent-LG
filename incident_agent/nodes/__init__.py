"""Node layer.

Node callables that LangGraph invokes with the graph state. Each node
adapts an agent (or a group of tools) to the `(state) -> partial_state`
contract LangGraph expects, translating state in and structured output
back into partial state updates via the state's reducers.
"""
