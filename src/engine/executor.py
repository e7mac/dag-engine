from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.engine.nodes.branch import BranchEvaluationError, evaluate_branch, evaluate_branch_all
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


async def _execute_node(
    workflow: WorkflowDef,
    run: WorkflowRun,
    node_id: str,
    sandbox_mode: bool,
    lock: asyncio.Lock | None = None,
) -> None:
    """Recursively execute a node and its successors."""
    if lock:
        async with lock:
            if node_id in run.node_runs:
                return
            # Reserve the node so no other concurrent path executes it
            run.node_runs[node_id] = NodeRun(
                node_id=node_id,
                status=NodeStatus.RUNNING,
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            run.execution_path.append(node_id)
    else:
        if node_id in run.node_runs:
            return
        run.execution_path.append(node_id)

    if node_id not in workflow.nodes:
        raise ValueError(f"Node '{node_id}' not found in workflow")

    node_def = workflow.nodes[node_id]

    if isinstance(node_def, ThirdPartyNodeDef):
        node_run = await execute_third_party(node_def, run.context, sandbox_mode)
        run.node_runs[node_id] = node_run

        if node_run.status == NodeStatus.FAILED:
            run.status = RunStatus.FAILED
            return

        await _execute_node(workflow, run, node_def.next, sandbox_mode, lock)

    elif isinstance(node_def, BranchNodeDef):
        node_run = NodeRun(
            node_id=node_id,
            status=NodeStatus.RUNNING,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        try:
            if node_def.concurrent:
                matches = evaluate_branch_all(node_def, run.context)
                node_run.status = NodeStatus.SUCCESS
                node_run.branch_taken = ",".join(label for _, label in matches)
                node_run.completed_at = datetime.now(timezone.utc).isoformat()
                run.node_runs[node_id] = node_run

                if len(matches) == 1:
                    await _execute_node(
                        workflow, run, matches[0][0], sandbox_mode, lock
                    )
                else:
                    concurrent_lock = asyncio.Lock()
                    tasks = [
                        _execute_node(
                            workflow, run, next_id, sandbox_mode, concurrent_lock
                        )
                        for next_id, _ in matches
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for result in results:
                        if isinstance(result, Exception):
                            run.status = RunStatus.FAILED
                            raise result
            else:
                next_node_id, edge_label = evaluate_branch(node_def, run.context)
                node_run.status = NodeStatus.SUCCESS
                node_run.branch_taken = edge_label
                node_run.completed_at = datetime.now(timezone.utc).isoformat()
                run.node_runs[node_id] = node_run

                await _execute_node(workflow, run, next_node_id, sandbox_mode, lock)

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
