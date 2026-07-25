"""Calculator tool -- arithmetic evaluation without `eval()`.

`eval()`/`exec()` on an LLM-supplied expression is a classic injection
vector (arbitrary code execution via `__import__('os').system(...)`-style
payloads). Instead we parse the expression into an AST and walk it
ourselves, only ever evaluating a small allowlist of node types
(numeric literals, +-*/%**//, unary +/-, and a handful of named
functions) -- anything else (attribute access, subscripts, calls to
unlisted names, comprehensions, ...) raises before any evaluation happens.
"""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable

from langchain_core.tools import tool

from incident_agent.tools.base import run_structured

_BINARY_OPERATORS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_ALLOWED_FUNCTIONS: dict[str, Callable[..., float]] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
}


class UnsupportedExpressionError(ValueError):
    """Raised when the expression contains anything outside the safe subset."""


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        return _BINARY_OPERATORS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_FUNCTIONS:
        args = [_eval_node(arg) for arg in node.args]
        return _ALLOWED_FUNCTIONS[node.func.id](*args)
    raise UnsupportedExpressionError(f"Unsupported expression element: {type(node).__name__}")


def _calculate(expression: str) -> dict:
    tree = ast.parse(expression, mode="eval")
    value = _eval_node(tree)
    return {"expression": expression, "result": value}


@tool
def calculator(expression: str) -> str:
    """Evaluate an arithmetic expression, e.g. '(842.3 - 25) / 25 * 100' to
    compute a percentage change. Supports +-*/%**//, unary +/-, and the
    functions abs/round/min/max/sqrt/log/log10. No variables, no imports.
    """
    return run_structured("calculator", lambda: _calculate(expression))
