"""Tool layer.

LangChain-compatible tools (`@tool` / `BaseTool`) exposed to agents:
vector search, SQL, knowledge base search, REST API calls, a sandboxed
Python REPL, log parsing, metrics collection, and mocked infrastructure
integrations (Kubernetes, Kafka, Postgres, Redis). Every tool returns a
structured, schema-validated JSON payload -- never free text.
"""
