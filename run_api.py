"""Convenience entry point: `python run_api.py`.

Equivalent to `uvicorn incident_agent.api.app:create_app --factory`, kept
as a plain script for the common case of "just start the server" without
remembering uvicorn's factory-import syntax.
"""

from __future__ import annotations

import uvicorn

from incident_agent.config.settings import get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "incident_agent.api.app:create_app",
        factory=True,
        host=settings.api.host,
        port=settings.api.port,
        reload=settings.debug,
    )
