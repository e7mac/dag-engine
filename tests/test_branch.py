from __future__ import annotations

import pytest

from src.engine.nodes.branch import BranchEvaluationError, evaluate_branch, evaluate_condition
from src.types import (
    BranchCondition,
    BranchEdge,
    BranchNodeDef,
    Operator,
)


# --- evaluate_condition tests ---


def test_equals_true():
    assert evaluate_condition("hello", Operator.EQUALS, "hello") is True


def test_equals_false():
    assert evaluate_condition("hello", Operator.EQUALS, "world") is False


def test_equals_numeric():
    assert evaluate_condition(42, Operator.EQUALS, 42) is True


def test_equals_bool():
    assert evaluate_condition(True, Operator.EQUALS, True) is True
    assert evaluate_condition(False, Operator.EQUALS, True) is False


def test_contains_string():
    assert evaluate_condition("hello world", Operator.CONTAINS, "world") is True
    assert evaluate_condition("hello world", Operator.CONTAINS, "xyz") is False


def test_contains_list():
    assert evaluate_condition(["a", "b", "c"], Operator.CONTAINS, "b") is True
    assert evaluate_condition(["a", "b", "c"], Operator.CONTAINS, "x") is False


def test_gt():
    assert evaluate_condition(10, Operator.GT, 5) is True
    assert evaluate_condition(5, Operator.GT, 10) is False
    assert evaluate_condition(5, Operator.GT, 5) is False


def test_lt():
    assert evaluate_condition(3, Operator.LT, 5) is True
    assert evaluate_condition(5, Operator.LT, 3) is False
    assert evaluate_condition(5, Operator.LT, 5) is False


def test_exists_present():
    assert evaluate_condition("value", Operator.EXISTS, None) is True


def test_exists_none():
    assert evaluate_condition(None, Operator.EXISTS, None) is False


# --- evaluate_branch tests ---


def _make_branch(
    edges: list[BranchEdge],
    default_next: str | None = None,
) -> BranchNodeDef:
    return BranchNodeDef(
        id="test_branch",
        type="branch",
        label="Test Branch",
        edges=edges,
        default_next=default_next,
    )


def test_branch_first_match():
    branch = _make_branch(
        edges=[
            BranchEdge(
                label="yes",
                condition=BranchCondition(field="status", operator=Operator.EQUALS, value="ok"),
                next="node_a",
            ),
            BranchEdge(
                label="no",
                condition=BranchCondition(field="status", operator=Operator.EQUALS, value="fail"),
                next="node_b",
            ),
        ]
    )

    next_id, label = evaluate_branch(branch, {"status": "ok"})
    assert next_id == "node_a"
    assert label == "yes"


def test_branch_second_match():
    branch = _make_branch(
        edges=[
            BranchEdge(
                label="high",
                condition=BranchCondition(field="score", operator=Operator.GT, value=80),
                next="node_high",
            ),
            BranchEdge(
                label="low",
                condition=BranchCondition(field="score", operator=Operator.LT, value=50),
                next="node_low",
            ),
        ]
    )

    next_id, label = evaluate_branch(branch, {"score": 30})
    assert next_id == "node_low"
    assert label == "low"


def test_branch_default_next():
    branch = _make_branch(
        edges=[
            BranchEdge(
                label="match",
                condition=BranchCondition(field="x", operator=Operator.EQUALS, value="yes"),
                next="node_match",
            ),
        ],
        default_next="node_default",
    )

    next_id, label = evaluate_branch(branch, {"x": "nope"})
    assert next_id == "node_default"
    assert label == "default"


def test_branch_no_match_no_default_raises():
    branch = _make_branch(
        edges=[
            BranchEdge(
                label="only",
                condition=BranchCondition(field="x", operator=Operator.EQUALS, value="yes"),
                next="node_a",
            ),
        ],
        default_next=None,
    )

    with pytest.raises(BranchEvaluationError, match="No matching edge"):
        evaluate_branch(branch, {"x": "no"})


def test_branch_dot_notation_context():
    """Branch resolves nested dot-notation fields against context."""
    branch = _make_branch(
        edges=[
            BranchEdge(
                label="in_stock",
                condition=BranchCondition(
                    field="nodes.inventory.response.in_stock",
                    operator=Operator.EQUALS,
                    value=True,
                ),
                next="ship",
            ),
        ],
        default_next="backorder",
    )

    context = {"nodes": {"inventory": {"response": {"in_stock": True}}}}
    next_id, label = evaluate_branch(branch, context)
    assert next_id == "ship"
    assert label == "in_stock"


def test_branch_exists_operator():
    branch = _make_branch(
        edges=[
            BranchEdge(
                label="has_token",
                condition=BranchCondition(
                    field="auth_token",
                    operator=Operator.EXISTS,
                ),
                next="authenticated",
            ),
        ],
        default_next="login",
    )

    # Token present
    next_id, _ = evaluate_branch(branch, {"auth_token": "abc123"})
    assert next_id == "authenticated"

    # Token absent
    next_id, _ = evaluate_branch(branch, {})
    assert next_id == "login"


def test_branch_contains_operator():
    branch = _make_branch(
        edges=[
            BranchEdge(
                label="has_admin",
                condition=BranchCondition(
                    field="roles",
                    operator=Operator.CONTAINS,
                    value="admin",
                ),
                next="admin_panel",
            ),
        ],
        default_next="user_panel",
    )

    next_id, _ = evaluate_branch(branch, {"roles": ["user", "admin"]})
    assert next_id == "admin_panel"

    next_id, _ = evaluate_branch(branch, {"roles": ["user"]})
    assert next_id == "user_panel"
