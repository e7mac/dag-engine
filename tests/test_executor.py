from __future__ import annotations

import json
from pathlib import Path

import pytest
from src.engine.executor import execute_workflow, resume_workflow
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


def _resumable_workflow() -> WorkflowDef:
    """A -> B -> end. B has no mock so it fails on first run."""
    return WorkflowDef(
        id="test-resume",
        name="Resume Test",
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
                    url="http://localhost:1/will-fail",
                    method="POST",
                    mock=None,
                    retry=RetryConfig(max_attempts=1, backoff_ms=0),
                    timeout_ms=100,
                ),
                next="end",
            ),
            "end": EndNodeDef(id="end", type="end", label="Done"),
        },
    )


async def test_resume_skips_successful_nodes():
    """Node A succeeds, node B fails. After fixing B's mock and resuming,
    node A is not re-executed and B + end complete successfully."""
    workflow = _resumable_workflow()

    # First run — node B fails (no mock, unreachable URL)
    run = await execute_workflow(workflow, sandbox_mode=True)
    assert run.status == RunStatus.FAILED
    assert run.node_runs["a"].status == NodeStatus.SUCCESS
    assert run.node_runs["b"].status == NodeStatus.FAILED

    # Record node A's original completed_at to verify it wasn't re-executed
    a_completed_at = run.node_runs["a"].completed_at

    # Fix node B by adding a mock
    b_node = workflow.nodes["b"]
    assert isinstance(b_node, ThirdPartyNodeDef)
    b_node.config.mock = MockConfig(status=200, body={"fixed": True})

    # Resume the failed run
    resumed = await resume_workflow(workflow, run)
    assert resumed.status == RunStatus.COMPLETED
    assert resumed.node_runs["a"].completed_at == a_completed_at  # Not re-executed
    assert resumed.node_runs["b"].status == NodeStatus.SUCCESS
    assert resumed.node_runs["b"].output == {"status": 200, "body": {"fixed": True}}
    assert resumed.node_runs["end"].status == NodeStatus.SUCCESS


async def test_resume_rejects_non_failed_run():
    """Resuming a completed run should raise ValueError."""
    workflow = _simple_workflow()
    run = await execute_workflow(workflow, sandbox_mode=True)
    assert run.status == RunStatus.COMPLETED

    with pytest.raises(ValueError, match="Can only resume failed runs"):
        await resume_workflow(workflow, run)


async def test_resume_preserves_context():
    """Resumed run keeps context from successful nodes so downstream
    template references still work."""
    workflow = _resumable_workflow()

    # First run — A succeeds and writes to context, B fails
    run = await execute_workflow(workflow, sandbox_mode=True)
    assert run.status == RunStatus.FAILED
    assert run.context["nodes"]["a"]["response"] == {"result": "ok"}

    # Fix B and resume
    b_node = workflow.nodes["b"]
    assert isinstance(b_node, ThirdPartyNodeDef)
    b_node.config.mock = MockConfig(status=200, body={"fixed": True})

    resumed = await resume_workflow(workflow, run)
    assert resumed.status == RunStatus.COMPLETED
    # Context from node A still present
    assert resumed.context["nodes"]["a"]["response"] == {"result": "ok"}
    # Context from node B now present too
    assert resumed.context["nodes"]["b"]["response"] == {"fixed": True}
