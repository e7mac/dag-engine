from __future__ import annotations

from src.types import (
    BranchCondition,
    BranchEdge,
    BranchNodeDef,
    EndNodeDef,
    MockConfig,
    Operator,
    ThirdPartyConfig,
    ThirdPartyNodeDef,
    WorkflowDef,
)
from src.validation.dag_validator import validate_workflow


def _valid_workflow() -> WorkflowDef:
    return WorkflowDef(
        id="valid",
        name="Valid Workflow",
        start_node_id="a",
        nodes={
            "a": ThirdPartyNodeDef(
                id="a",
                type="third_party",
                label="Step A",
                config=ThirdPartyConfig(
                    url="https://example.com",
                    method="POST",
                    mock=MockConfig(status=200, body={}),
                ),
                next="end",
            ),
            "end": EndNodeDef(id="end", type="end", label="Done"),
        },
    )


def test_valid_workflow_passes():
    errors = validate_workflow(_valid_workflow())
    assert errors == []


def test_missing_start_node():
    wf = WorkflowDef(
        id="bad-start",
        name="Bad Start",
        start_node_id="nonexistent",
        nodes={
            "a": EndNodeDef(id="a", type="end", label="End"),
        },
    )
    errors = validate_workflow(wf)
    assert any("start_node_id" in e for e in errors)


def test_missing_next_ref():
    wf = WorkflowDef(
        id="bad-next",
        name="Bad Next",
        start_node_id="a",
        nodes={
            "a": ThirdPartyNodeDef(
                id="a",
                type="third_party",
                label="Step A",
                config=ThirdPartyConfig(
                    url="https://example.com",
                    method="POST",
                    mock=MockConfig(status=200, body={}),
                ),
                next="does_not_exist",
            ),
        },
    )
    errors = validate_workflow(wf)
    assert any("does_not_exist" in e for e in errors)


def test_unreachable_node():
    wf = WorkflowDef(
        id="unreachable",
        name="Unreachable",
        start_node_id="a",
        nodes={
            "a": ThirdPartyNodeDef(
                id="a",
                type="third_party",
                label="Step A",
                config=ThirdPartyConfig(
                    url="https://example.com",
                    method="POST",
                    mock=MockConfig(status=200, body={}),
                ),
                next="end",
            ),
            "end": EndNodeDef(id="end", type="end", label="Done"),
            "orphan": EndNodeDef(id="orphan", type="end", label="Orphan"),
        },
    )
    errors = validate_workflow(wf)
    assert any("orphan" in e and "not reachable" in e for e in errors)


def test_cycle_detection():
    wf = WorkflowDef(
        id="cycle",
        name="Cycle",
        start_node_id="a",
        nodes={
            "a": ThirdPartyNodeDef(
                id="a",
                type="third_party",
                label="A",
                config=ThirdPartyConfig(
                    url="https://example.com",
                    method="POST",
                    mock=MockConfig(status=200, body={}),
                ),
                next="b",
            ),
            "b": ThirdPartyNodeDef(
                id="b",
                type="third_party",
                label="B",
                config=ThirdPartyConfig(
                    url="https://example.com",
                    method="POST",
                    mock=MockConfig(status=200, body={}),
                ),
                next="a",  # Cycle back to a
            ),
        },
    )
    errors = validate_workflow(wf)
    assert any("Cycle" in e or "cycle" in e.lower() for e in errors)


def test_branch_with_missing_edge_target():
    wf = WorkflowDef(
        id="bad-branch",
        name="Bad Branch",
        start_node_id="a",
        nodes={
            "a": BranchNodeDef(
                id="a",
                type="branch",
                label="Branch",
                edges=[
                    BranchEdge(
                        label="yes",
                        condition=BranchCondition(
                            field="foo",
                            operator=Operator.EQUALS,
                            value=True,
                        ),
                        next="nowhere",
                    ),
                ],
                default_next="end",
            ),
            "end": EndNodeDef(id="end", type="end", label="End"),
        },
    )
    errors = validate_workflow(wf)
    assert any("nowhere" in e for e in errors)


def test_valid_branch_workflow():
    wf = WorkflowDef(
        id="valid-branch",
        name="Valid Branch",
        start_node_id="start",
        nodes={
            "start": ThirdPartyNodeDef(
                id="start",
                type="third_party",
                label="Start",
                config=ThirdPartyConfig(
                    url="https://example.com",
                    method="POST",
                    mock=MockConfig(status=200, body={}),
                ),
                next="branch",
            ),
            "branch": BranchNodeDef(
                id="branch",
                type="branch",
                label="Check",
                edges=[
                    BranchEdge(
                        label="yes",
                        condition=BranchCondition(
                            field="foo", operator=Operator.EQUALS, value=True
                        ),
                        next="end_a",
                    ),
                ],
                default_next="end_b",
            ),
            "end_a": EndNodeDef(id="end_a", type="end", label="A"),
            "end_b": EndNodeDef(id="end_b", type="end", label="B"),
        },
    )
    errors = validate_workflow(wf)
    assert errors == []


def test_valid_upstream_template_reference():
    """Template referencing an upstream node should pass validation."""
    wf = WorkflowDef(
        id="valid-ref",
        name="Valid Ref",
        start_node_id="fetch",
        nodes={
            "fetch": ThirdPartyNodeDef(
                id="fetch",
                type="third_party",
                label="Fetch",
                config=ThirdPartyConfig(
                    url="https://example.com",
                    method="POST",
                    mock=MockConfig(status=200, body={"user_id": 1}),
                ),
                next="use_fetch",
            ),
            "use_fetch": ThirdPartyNodeDef(
                id="use_fetch",
                type="third_party",
                label="Use Fetch",
                config=ThirdPartyConfig(
                    url="https://example.com/{{nodes.fetch.response.user_id}}",
                    method="POST",
                    mock=MockConfig(status=200, body={}),
                ),
                next="end",
            ),
            "end": EndNodeDef(id="end", type="end", label="Done"),
        },
    )
    errors = validate_workflow(wf)
    assert errors == []


def test_template_reference_to_nonexistent_node():
    """Template referencing a node that doesn't exist should fail validation."""
    wf = WorkflowDef(
        id="bad-ref",
        name="Bad Ref",
        start_node_id="a",
        nodes={
            "a": ThirdPartyNodeDef(
                id="a",
                type="third_party",
                label="A",
                config=ThirdPartyConfig(
                    url="https://example.com",
                    method="POST",
                    body={"val": "{{nodes.ghost.response.data}}"},
                    mock=MockConfig(status=200, body={}),
                ),
                next="end",
            ),
            "end": EndNodeDef(id="end", type="end", label="Done"),
        },
    )
    errors = validate_workflow(wf)
    assert len(errors) == 1
    assert "ghost" in errors[0]
    assert "does not exist" in errors[0]


def test_template_reference_to_downstream_node():
    """Template referencing a downstream (not upstream) node should fail validation."""
    wf = WorkflowDef(
        id="downstream-ref",
        name="Downstream Ref",
        start_node_id="a",
        nodes={
            "a": ThirdPartyNodeDef(
                id="a",
                type="third_party",
                label="A",
                config=ThirdPartyConfig(
                    url="https://example.com/{{nodes.b.response.value}}",
                    method="POST",
                    mock=MockConfig(status=200, body={}),
                ),
                next="b",
            ),
            "b": ThirdPartyNodeDef(
                id="b",
                type="third_party",
                label="B",
                config=ThirdPartyConfig(
                    url="https://example.com",
                    method="POST",
                    mock=MockConfig(status=200, body={"value": 42}),
                ),
                next="end",
            ),
            "end": EndNodeDef(id="end", type="end", label="Done"),
        },
    )
    errors = validate_workflow(wf)
    assert len(errors) == 1
    assert "not upstream" in errors[0]
    assert "'a'" in errors[0]
    assert "'b'" in errors[0]
