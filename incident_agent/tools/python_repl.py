"""Python REPL tool -- sandboxed-ish arithmetic/data-wrangling scratchpad.

This executes LLM-generated code, which is inherently risky (arbitrary
code execution). We do not claim full sandboxing -- true isolation would
mean a subprocess/container boundary, which is out of scope here -- but
we apply concrete, real defenses rather than a bare `eval`/`exec`:

1. AST validation *before* execution: reject `import`/`from ... import`
   (a curated set of safe modules is already in the namespace) and reject
   any dunder name/attribute access (blocks the classic
   `().__class__.__bases__` sandbox-escape family).
2. A restricted `__builtins__` allowlist -- no `open`, `eval`, `exec`,
   `__import__`, `input`, `compile`.
3. A soft timeout via a daemon thread: if execution exceeds the timeout we
   report a timeout error and return immediately rather than blocking the
   graph indefinitely. The runaway thread is not force-killed (Python has
   no safe API for that) -- it is abandoned as a daemon thread, which is
   an accepted limitation for this project's scope, not a claim of hard
   resource isolation.
"""

from __future__ import annotations

import ast
import builtins
import contextlib
import io
import math
import statistics
import threading
from typing import Any

from langchain_core.tools import tool

from incident_agent.tools.base import run_structured

_TIMEOUT_SECONDS = 5.0

_SAFE_BUILTINS: dict[str, Any] = {
    name: getattr(builtins, name)
    for name in (
        "abs", "min", "max", "sum", "len", "range", "sorted", "round",
        "enumerate", "zip", "map", "filter", "any", "all", "list", "dict",
        "set", "tuple", "str", "int", "float", "bool", "print",
    )
}
_SAFE_MODULES: dict[str, Any] = {"math": math, "statistics": statistics}


class PythonREPLSecurityError(ValueError):
    """Raised when submitted code fails the static safety check."""


class PythonREPLTimeoutError(TimeoutError):
    """Raised when execution exceeds the soft timeout."""


def _validate_ast(code: str) -> ast.Module:
    tree = ast.parse(code, mode="exec")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise PythonREPLSecurityError(
                "import statements are not permitted; math and statistics are already available."
            )
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise PythonREPLSecurityError(f"access to dunder attribute '{node.attr}' is not permitted.")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise PythonREPLSecurityError(f"access to dunder name '{node.id}' is not permitted.")
    return tree


def _run_in_namespace(tree: ast.Module, namespace: dict[str, Any], stdout: io.StringIO) -> None:
    with contextlib.redirect_stdout(stdout):
        exec(compile(tree, "<incident_agent_repl>", "exec"), namespace)  # noqa: S102 -- validated above


def _execute(code: str) -> dict:
    tree = _validate_ast(code)
    namespace: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS, **_SAFE_MODULES}
    stdout = io.StringIO()

    error: BaseException | None = None

    def target() -> None:
        nonlocal error
        try:
            _run_in_namespace(tree, namespace, stdout)
        except BaseException as exc:  # noqa: BLE001 -- surfaced to the caller, not swallowed
            error = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=_TIMEOUT_SECONDS)
    if thread.is_alive():
        raise PythonREPLTimeoutError(f"Execution exceeded the {_TIMEOUT_SECONDS}s timeout.")
    if error is not None:
        raise error

    result_value = namespace.get("result")
    return {
        "stdout": stdout.getvalue(),
        "result": repr(result_value) if result_value is not None else None,
    }


@tool
def python_repl(code: str) -> str:
    """Execute a short Python snippet for calculations or data wrangling
    during an investigation (e.g. computing a percentage change, summarizing
    a list of numbers). `math` and `statistics` are pre-imported; no other
    imports are permitted. Assign your final answer to a variable named
    `result` to have it captured; anything printed is captured as `stdout`.
    """
    return run_structured("python_repl", lambda: _execute(code))
