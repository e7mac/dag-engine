from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.engine.executor import execute_workflow
from src.types import (
    BranchCondition,
    BranchEdge,
    BranchNodeDef,
    EndNodeDef,
    MockConfig,
    NodeStatus,
    Operator,
    RetryConfig,
    RunStatus,
    ThirdPartyConfig,
    ThirdPartyNodeDef,
    WorkflowDef,
)


def _simple_workflow() -> WorkflowDef:
    """A -> B -> end"""
    return WorkflowDef(
        id="test-simple",
        name="Simple Test",
        start_node_id="a",
        nodes={
            "a": ThirdPartyNodeDef(
                id="a",
                type="third_party",
                label="Step A",
                config=ThirdPartyConfig(
                    url="https://example.com/a",
                    method="POST",
                    mock=MockConfig(status=200, body={"result": "ok"}),
                ),
                next="b",
            ),
            "b": ThirdPartyNodeDef(
                id="b",
                type="third_party",
                label="Step B",
                config=ThirdPartyConfig(
                    url="https://example.com/b",
                    method="POST",
                    mock=MockConfig(status=200, body={"done": True}),
                ),
                next="end",
            ),
            "end": EndNodeDef(id="end", type="end", label="Done"),
        },
    )


def _branching_workflow() -> WorkflowDef:
    """A -> branch -> yes(B) -> end_ok / no -> end_fail"""
    return WorkflowDef(
        id="test-branch",
        name="Branch Test",
        start_node_id="a",
        nodes={
            "a": ThirdPartyNodeDef(
                id="a",
                type="third_party",
                label="Fetch Data",
                config=ThirdPartyConfig(
                    url="https://example.com/a",
                    method="POST",
                    mock=MockConfig(status=200, body={"approved": True}),
                ),
                next="branch",
            ),
            "branch": BranchNodeDef(
                id="branch",
                type="branch",
                label="Approved?",
                edges=[
                    BranchEdge(
                        label="yes",
                        condition=BranchCondition(
                            field="nodes.a.response.approved",
                            operator=Operator.EQUALS,
                            value=True,
                        ),
                        next="b",
                    ),
                    BranchEdge(
                        label="no",
                        condition=BranchCondition(
                            field="nodes.a.response.approved",
                            operator=Operator.EQUALS,
                            value=False,
                        ),
                        next="end_fail",
                    ),
                ],
            ),
            "b": ThirdPartyNodeDef(
                id="b",
                type="third_party",
                label="Process",
                config=ThirdPartyConfig(
                    url="https://example.com/b",
                    method="POST",
                    mock=MockConfig(status=200, body={"processed": True}),
                ),
                next="end_ok",
            ),
            "end_ok": EndNodeDef(id="end_ok", type="end", label="Success"),
            "end_fail": EndNodeDef(id="end_fail", type="end", label="Rejected"),
        },
    )


async def test_happy_path_simple():
    workflow = _simple_workflow()
    run = await execute_workflow(workflow, sandbox_mode=True)

    assert run.status == RunStatus.COMPLETED
    assert run.execution_path == ["a", "b", "end"]
    assert run.node_runs["a"].status == NodeStatus.SUCCESS
    assert run.node_runs["b"].status == NodeStatus.SUCCESS
    assert run.node_runs["end"].status == NodeStatus.SUCCESS
    assert run.context["nodes"]["a"]["response"] == {"result": "ok"}
    assert run.context["nodes"]["b"]["response"] == {"done": True}


async def test_branch_routing_yes():
    workflow = _branching_workflow()
    run = await execute_workflow(workflow, sandbox_mode=True)

    assert run.status == RunStatus.COMPLETED
    assert "branch" in run.execution_path
    assert run.node_runs["branch"].branch_taken == "yes"
    assert "b" in run.execution_path
    assert "end_ok" in run.execution_path


async def test_branch_routing_no():
    workflow = _branching_workflow()
    # Override mock to return approved=False
    a_node = workflow.nodes["a"]
    assert isinstance(a_node, ThirdPartyNodeDef)
    a_node.config.mock = MockConfig(status=200, body={"approved": False})

    run = await execute_workflow(workflow, sandbox_mode=True)

    assert run.status == RunStatus.COMPLETED
    assert run.node_runs["branch"].branch_taken == "no"
    assert "end_fail" in run.execution_path


async def test_sandbox_uses_mock():
    workflow = _simple_workflow()
    run = await execute_workflow(workflow, sandbox_mode=True)

    assert run.sandbox_mode is True
    assert run.node_runs["a"].output == {"status": 200, "body": {"result": "ok"}}
    assert run.node_runs["a"].attempts == 1


async def test_initial_context_passed():
    workflow = WorkflowDef(
        id="test-ctx",
        name="Context Test",
        start_node_id="a",
        nodes={
            "a": ThirdPartyNodeDef(
                id="a",
                type="third_party",
                label="Use Context",
                config=ThirdPartyConfig(
                    url="https://example.com/{{context.item_id}}",
                    method="POST",
                    body={"key": "{{context.api_key}}"},
                    mock=MockConfig(status=200, body={"ok": True}),
                ),
                next="end",
            ),
            "end": EndNodeDef(id="end", type="end", label="Done"),
        },
    )

    run = await execute_workflow(
        workflow,
        initial_context={"item_id": "42", "api_key": "secret"},
        sandbox_mode=True,
    )

    assert run.status == RunStatus.COMPLETED
    assert run.node_runs["a"].input["url"] == "https://example.com/42"
    assert run.node_runs["a"].input["body"] == {"key": "secret"}


async def test_order_fulfillment_example():
    """End-to-end test using the order_fulfillment.json example."""
    example_path = Path(__file__).parent.parent / "examples" / "order_fulfillment.json"
    data = json.loads(example_path.read_text())
    workflow = WorkflowDef.model_validate(data)

    run = await execute_workflow(
        workflow,
        initial_context={"sku": "WIDGET-001"},
        sandbox_mode=True,
    )

    assert run.status == RunStatus.COMPLETED
    assert "check_inventory" in run.execution_path
    assert "branch_in_stock" in run.execution_path
    assert run.node_runs["branch_in_stock"].branch_taken == "yes"
    assert "create_shipment" in run.execution_path
    assert "end_success" in run.execution_path


async def test_email_validation_example():
    """End-to-end test using the email_validation.json example."""
    example_path = Path(__file__).parent.parent / "examples" / "email_validation.json"
    data = json.loads(example_path.read_text())
    workflow = WorkflowDef.model_validate(data)

    run = await execute_workflow(
        workflow,
        initial_context={"email": "test@example.com", "ip": "1.2.3.4", "phone": "+1234567890"},
        sandbox_mode=True,
    )

    assert run.status == RunStatus.COMPLETED
    assert run.node_runs["email_valid"].branch_taken == "yes"
    assert run.node_runs["risk_level"].branch_taken == "low"
    assert "send_welcome" in run.execution_path
    assert "end_success" in run.execution_path
