from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from src.engine.executor import execute_workflow
from src.store.run_store import RunStore
from src.types import WorkflowDef, WorkflowRun
from src.validation.dag_validator import validate_workflow

logger = logging.getLogger(__name__)

app = FastAPI(title="DAG Workflow Engine", version="0.1.0")

# In-memory workflow registry and run store
_workflows: dict[str, WorkflowDef] = {}
_run_store = RunStore()

# Metrics counters
_metrics = {
    "runs_total": 0,
    "nodes_succeeded": 0,
    "nodes_failed": 0,
    "retries_total": 0,
}


class RunRequest(BaseModel):
    initial_context: dict[str, Any] = {}
    sandbox_mode: bool = False


class RunResponse(BaseModel):
    run_id: str


class ValidationResponse(BaseModel):
    valid: bool
    errors: list[str]


# --- Workflow endpoints ---


@app.post("/workflows", status_code=201)
async def register_workflow(workflow: WorkflowDef) -> WorkflowDef:
    _workflows[workflow.id] = workflow
    logger.info("workflow_registered", extra={"workflow_id": workflow.id})
    return workflow


@app.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str) -> WorkflowDef:
    if workflow_id not in _workflows:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    return _workflows[workflow_id]


@app.post("/workflows/{workflow_id}/validate")
async def validate_workflow_endpoint(workflow_id: str) -> ValidationResponse:
    if workflow_id not in _workflows:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    errors = validate_workflow(_workflows[workflow_id])
    return ValidationResponse(valid=len(errors) == 0, errors=errors)


@app.post("/workflows/{workflow_id}/run")
async def run_workflow(
    workflow_id: str,
    request: RunRequest,
    background_tasks: BackgroundTasks,
) -> RunResponse:
    if workflow_id not in _workflows:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")

    workflow = _workflows[workflow_id]

    # Validate before running
    errors = validate_workflow(workflow)
    if errors:
        raise HTTPException(status_code=400, detail={"validation_errors": errors})

    import uuid

    run_id = str(uuid.uuid4())
    _metrics["runs_total"] += 1

    async def _run() -> None:
        run = await execute_workflow(
            workflow,
            initial_context=request.initial_context,
            sandbox_mode=request.sandbox_mode,
        )
        # Overwrite the auto-generated run_id so we can track it
        run.run_id = run_id
        _run_store.save(run)

        # Update metrics
        for node_run in run.node_runs.values():
            if node_run.status.value == "success":
                _metrics["nodes_succeeded"] += 1
            elif node_run.status.value == "failed":
                _metrics["nodes_failed"] += 1
            if node_run.attempts > 1:
                _metrics["retries_total"] += node_run.attempts - 1

    background_tasks.add_task(_run)
    return RunResponse(run_id=run_id)


# --- Run endpoints ---


@app.get("/runs/{run_id}")
async def get_run(run_id: str) -> WorkflowRun:
    run = _run_store.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return run


class TraceNodeSummary(BaseModel):
    node_id: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: float | None = None
    status: str
    attempts: int = 0
    branch_taken: str | None = None


class TraceResponse(BaseModel):
    run_id: str
    execution_path: list[str]
    nodes: list[TraceNodeSummary]


@app.get("/runs/{run_id}/trace")
async def get_trace(run_id: str) -> TraceResponse:
    run = _run_store.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    nodes: list[TraceNodeSummary] = []
    for node_id in run.execution_path:
        node_run = run.node_runs.get(node_id)
        if node_run is None:
            continue

        duration_ms: float | None = None
        if node_run.started_at and node_run.completed_at:
            start = datetime.fromisoformat(node_run.started_at)
            end = datetime.fromisoformat(node_run.completed_at)
            duration_ms = (end - start).total_seconds() * 1000

        nodes.append(
            TraceNodeSummary(
                node_id=node_run.node_id,
                started_at=node_run.started_at,
                completed_at=node_run.completed_at,
                duration_ms=duration_ms,
                status=node_run.status.value,
                attempts=node_run.attempts,
                branch_taken=node_run.branch_taken,
            )
        )

    return TraceResponse(
        run_id=run.run_id,
        execution_path=run.execution_path,
        nodes=nodes,
    )


# --- Metrics endpoint ---


@app.get("/metrics")
async def metrics() -> str:
    lines = [
        f"# HELP runs_total Total workflow runs",
        f"# TYPE runs_total counter",
        f'runs_total {_metrics["runs_total"]}',
        f"# HELP nodes_succeeded Total successful node executions",
        f"# TYPE nodes_succeeded counter",
        f'nodes_succeeded {_metrics["nodes_succeeded"]}',
        f"# HELP nodes_failed Total failed node executions",
        f"# TYPE nodes_failed counter",
        f'nodes_failed {_metrics["nodes_failed"]}',
        f"# HELP retries_total Total retry attempts across all nodes",
        f"# TYPE retries_total counter",
        f'retries_total {_metrics["retries_total"]}',
    ]
    return "\n".join(lines) + "\n"
