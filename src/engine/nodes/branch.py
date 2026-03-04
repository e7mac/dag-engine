from __future__ import annotations

import logging
from typing import Any

from src.engine.nodes.base import resolve_dot_path_safe
from src.types import BranchNodeDef, NodeId, Operator

logger = logging.getLogger(__name__)


class BranchEvaluationError(Exception):
    pass


def evaluate_condition(field_value: Any, operator: Operator, expected: Any) -> bool:
    """Evaluate a single branch condition."""
    if operator == Operator.EQUALS:
        return field_value == expected
    elif operator == Operator.CONTAINS:
        if isinstance(field_value, str):
            return expected in field_value
        elif isinstance(field_value, list):
            return expected in field_value
        return False
    elif operator == Operator.GT:
        return float(field_value) > float(expected)
    elif operator == Operator.LT:
        return float(field_value) < float(expected)
    elif operator == Operator.EXISTS:
        return field_value is not None
    return False


def evaluate_branch(
    node_def: BranchNodeDef,
    context: dict[str, Any],
) -> tuple[NodeId, str]:
    """Evaluate branch edges and return (next_node_id, edge_label).

    Raises BranchEvaluationError if no edge matches and no default_next.
    """
    for edge in node_def.edges:
        found, field_value = resolve_dot_path_safe(context, edge.condition.field)

        if edge.condition.operator == Operator.EXISTS:
            if found and field_value is not None:
                logger.info(
                    "branch_taken",
                    extra={"node_id": node_def.id, "edge": edge.label},
                )
                return edge.next, edge.label
            continue

        if not found:
            continue

        if evaluate_condition(field_value, edge.condition.operator, edge.condition.value):
            logger.info(
                "branch_taken",
                extra={"node_id": node_def.id, "edge": edge.label},
            )
            return edge.next, edge.label

    if node_def.default_next:
        logger.info(
            "branch_default",
            extra={"node_id": node_def.id, "default_next": node_def.default_next},
        )
        return node_def.default_next, "default"

    raise BranchEvaluationError(
        f"No matching edge and no default_next for branch node '{node_def.id}'"
    )
