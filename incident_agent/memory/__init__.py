"""Memory layer.

Conversation, long-term, semantic, episodic, and checkpoint memory
stores. Backed by Chroma (semantic/episodic) and SQLite
(checkpoint/structured), exposed through a repository-pattern interface
so the storage backend can be swapped without touching callers.
"""
