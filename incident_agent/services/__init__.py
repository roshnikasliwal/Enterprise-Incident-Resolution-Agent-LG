"""Service layer.

Cross-cutting infrastructure services shared across agents/tools/graphs:
LLM client factory (Anthropic-first with OpenAI/Azure OpenAI fallback),
vector store service, embedding service, and database session
management. Services are injected into agents/tools rather than
constructed inline, keeping the codebase testable via dependency
injection.
"""
