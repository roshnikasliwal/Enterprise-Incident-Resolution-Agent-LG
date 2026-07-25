"""API layer.

FastAPI routers, request-scoped dependencies, and the ASGI application
factory. Talks only to controllers/, never directly to graphs/ or
agents/, keeping HTTP concerns isolated from orchestration logic.
"""
