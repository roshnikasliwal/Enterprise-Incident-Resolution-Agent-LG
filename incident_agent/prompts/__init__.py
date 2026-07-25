"""Prompt layer.

Versioned prompt templates for every agent, built with LangChain's
`ChatPromptTemplate`. Kept separate from agent logic so prompts can be
iterated on, tested, and traced (via LangSmith) independently of Python
code changes.
"""
