from __future__ import annotations

import re
from typing import Any


def resolve_dot_path(obj: Any, path: str) -> Any:
    """Resolve a dot-notation path against a nested dict/list structure.

    e.g. resolve_dot_path(ctx, "nodes.foo.response.bar")
    """
    parts = path.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(f"Key '{part}' not found in path '{path}'")
            current = current[part]
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise KeyError(f"Invalid index '{part}' in path '{path}'") from exc
        else:
            raise KeyError(f"Cannot traverse into {type(current).__name__} with key '{part}' in path '{path}'")
    return current


def resolve_dot_path_safe(obj: Any, path: str) -> tuple[bool, Any]:
    """Like resolve_dot_path but returns (found, value) instead of raising."""
    try:
        return True, resolve_dot_path(obj, path)
    except KeyError:
        return False, None


_TEMPLATE_RE = re.compile(r"\{\{(.*?)\}\}")


def resolve_template(value: Any, context: dict[str, Any]) -> Any:
    """Recursively resolve {{context.path}} placeholders in a value."""
    if isinstance(value, str):
        # If the entire string is a single placeholder, return the raw value (preserving type)
        full_match = re.fullmatch(r"\{\{context\.(.*?)\}\}", value)
        if full_match:
            return resolve_dot_path(context, full_match.group(1))
        # Otherwise do string interpolation
        def _replace(m: re.Match[str]) -> str:
            expr = m.group(1).strip()
            if expr.startswith("context."):
                expr = expr[len("context."):]
            return str(resolve_dot_path(context, expr))
        return _TEMPLATE_RE.sub(_replace, value)
    elif isinstance(value, dict):
        return {k: resolve_template(v, context) for k, v in value.items()}
    elif isinstance(value, list):
        return [resolve_template(item, context) for item in value]
    return value
