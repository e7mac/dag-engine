from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.engine.nodes.branch import BranchEvaluationError, evaluate_branch
from src.engine.nodes.third_party import execute_third_party
from src.types import (
    BranchNodeDef,
    EndNodeDef,
    NodeRun,
    NodeStatus,
    RunStatus,
    ThirdPartyNodeDef,
    WorkflowDef,
    WorkflowRun,
)

logger = logging.getLogger(__name__)


async def execute_workflow(
    workflow: WorkflowDef,
    initial_context: dict[str, Any] | None = None,
    sandbox_mode: bool = False,
) -> WorkflowRun:
    """Execute a workflow DAG from start to end."""
    run = WorkflowRun(
        run_id=str(uuid.uuid4()),
        workflow_id=workflow.id,
        status=RunStatus.RUNNING,
        started_at=datetime.now(timezone.utc).isoformat(),
        context=dict(initial_context) if initial_context else {},
        sandbox_mode=sandbox_mode,
    )

    logger.info("workflow_started", extra={"run_id": run.run_id, "workflow_id": workflow.id})

    try:
        await _execute_node(workflow, run, workflow.start_node_id, sandbox_mode)
        if run.status != RunStatus.FAILED:
            run.status = RunStatus.COMPLETED
    except Exception as exc:
        run.status = RunStatus.FAILED
        logger.error("workflow_error", extra={"run_id": run.run_id, "error": str(exc)})

    run.completed_at = datetime.now(timezone.utc).isoformat()
    logger.info(
        "workflow_completed",
        extra={"run_id": run.run_id, "status": run.status.value},
    )
    return run


async def resume_workflow(
    workflow: WorkflowDef,
    run: WorkflowRun,
) -> WorkflowRun:
    """Resume a failed workflow run from the last successful node."""
    if run.status != RunStatus.FAILED:
        raise ValueError(f"Can only resume failed runs, got status '{run.status.value}'")

    # Remove FAILED node entries so they get re-executed
    failed_node_ids = [
        nid for nid, nr in run.node_runs.items() if nr.status == NodeStatus.FAILED
    ]
    for nid in failed_node_ids:
        del run.node_runs[nid]
        if nid in run.execution_path:
            run.execution_path.remove(nid)

    run.status = RunStatus.RUNNING
    run.completed_at = None

    logger.info(
        "workflow_resumed",
        extra={"run_id": run.run_id, "workflow_id": workflow.id, "skipping": list(run.node_runs.keys())},
    )

    try:
        await _execute_node(workflow, run, workflow.start_node_id, run.sandbox_mode)
        if run.status != RunStatus.FAILED:
            run.status = RunStatus.COMPLETED
    except Exception as exc:
        run.status = RunStatus.FAILED
        logger.error("workflow_resume_error", extra={"run_id": run.run_id, "error": str(exc)})

    run.completed_at = datetime.now(timezone.utc).isoformat()
    return run


async def _execute_node(
    workflow: WorkflowDef,
    run: WorkflowRun,
    node_id: str,
    sandbox_mode: bool,
) -> None:
    """Recursively execute a node and its successors."""
    if node_id not in workflow.nodes:
        raise ValueError(f"Node '{node_id}' not found in workflow")

    node_def = workflow.nodes[node_id]

    # Skip nodes that already succeeded (supports resume) — but still follow edges
    existing = run.node_runs.get(node_id)
    if existing is not None and existing.status == NodeStatus.SUCCESS:
        if isinstance(node_def, ThirdPartyNodeDef):
            await _execute_node(workflow, run, node_def.next, sandbox_mode)
        elif isinstance(node_def, BranchNodeDef) and existing.branch_taken:
            # Re-follow the same branch edge that was taken before
            for edge in node_def.edges:
                if edge.label == existing.branch_taken:
                    await _execute_node(workflow, run, edge.next, sandbox_mode)
                    return
            if node_def.default_next and existing.branch_taken == "default":
                await _execute_node(workflow, run, node_def.default_next, sandbox_mode)
        return

    run.execution_path.append(node_id)

    if isinstance(node_def, ThirdPartyNodeDef):
        node_run = await execute_third_party(node_def, run.context, sandbox_mode)
        run.node_runs[node_id] = node_run

        if node_run.status == NodeStatus.FAILED:
            run.status = RunStatus.FAILED
            return

        await _execute_node(workflow, run, node_def.next, sandbox_mode)

    elif isinstance(node_def, BranchNodeDef):
        node_run = NodeRun(
            node_id=node_id,
            status=NodeStatus.RUNNING,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        try:
            next_node_id, edge_label = evaluate_branch(node_def, run.context)
            node_run.status = NodeStatus.SUCCESS
            node_run.branch_taken = edge_label
            node_run.completed_at = datetime.now(timezone.utc).isoformat()
            run.node_runs[node_id] = node_run

            await _execute_node(workflow, run, next_node_id, sandbox_mode)

        except BranchEvaluationError as exc:
            node_run.status = NodeStatus.FAILED
            node_run.error = str(exc)
            node_run.completed_at = datetime.now(timezone.utc).isoformat()
            run.node_runs[node_id] = node_run
            run.status = RunStatus.FAILED

    elif isinstance(node_def, EndNodeDef):
        node_run = NodeRun(
            node_id=node_id,
            status=NodeStatus.SUCCESS,
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        run.node_runs[node_id] = node_run
