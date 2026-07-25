"""Tiny shared helper for calling a LangChain tool and parsing its
`ToolResult` JSON envelope back into a dict, used by every evidence node.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import BaseTool


def invoke_tool(tool: BaseTool, **kwargs: Any) -> dict[str, Any]:
    """Invoke `tool` and parse its JSON `ToolResult` envelope.

    Never raises on a tool-level failure -- `status`/`error_message` in the
    returned dict communicate that (see `tools/base.run_structured`); this
    only raises if the tool's own JSON serialization contract is broken,
    which would be a bug in the tool itself.
    """
    return json.loads(tool.invoke(kwargs))


def tool_succeeded(payload: dict[str, Any]) -> bool:
    return payload.get("status") == "success"
