from __future__ import annotations

import logging
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.engine.executor import execute_workflow
from src.store.run_store import RunStore
from src.types import WorkflowDef, WorkflowRun
from src.validation.dag_validator import validate_workflow

logger = logging.getLogger(__name__)

app = FastAPI(title="DAG Workflow Engine", version="0.1.0")

# --- Static files & root redirect ---
_static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

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


# --- Root redirect ---


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(str(_static_dir / "index.html"))


# --- Workflow endpoints ---


@app.get("/workflows")
async def list_workflows() -> list[WorkflowDef]:
    return list(_workflows.values())


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


@app.get("/runs")
async def list_runs(workflow_id: str | None = None) -> list[WorkflowRun]:
    return _run_store.list_runs(workflow_id)


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


# --- Test endpoints ---

_flaky_counter: dict[str, int] = {}


@app.get("/test/flaky")
async def flaky_endpoint(fail_count: int = 2) -> dict:
    """Fails the first `fail_count` calls, then succeeds. Resets after success.
    Use ?fail_count=N to control how many failures before success."""
    import uuid

    # Track by a simple global counter
    key = "global"
    _flaky_counter.setdefault(key, 0)
    _flaky_counter[key] += 1

    if _flaky_counter[key] <= fail_count:
        raise HTTPException(
            status_code=500,
            detail=f"Simulated failure ({_flaky_counter[key]}/{fail_count})",
        )

    # Success — reset counter for next test
    _flaky_counter[key] = 0
    return {"status": "ok", "message": "Recovered after retries", "failed_attempts": fail_count}


# --- Stats endpoint ---


def _run_duration_ms(run: WorkflowRun) -> float | None:
    """Compute duration in ms from started_at / completed_at ISO strings."""
    if not run.started_at or not run.completed_at:
        return None
    try:
        start = datetime.fromisoformat(run.started_at)
        end = datetime.fromisoformat(run.completed_at)
        return (end - start).total_seconds() * 1000
    except (ValueError, TypeError):
        return None


@app.get("/stats")
async def stats() -> dict[str, Any]:
    all_runs = _run_store.list_runs()

    completed = [r for r in all_runs if r.status.value == "completed"]
    failed = [r for r in all_runs if r.status.value == "failed"]
    finished = len(completed) + len(failed)
    success_rate = (len(completed) / finished * 100) if finished > 0 else 0.0

    durations = [d for r in all_runs if (d := _run_duration_ms(r)) is not None]
    if durations:
        sorted_d = sorted(durations)
        p95_idx = int(len(sorted_d) * 0.95)
        p95_idx = min(p95_idx, len(sorted_d) - 1)
        latency = {
            "avg_ms": round(statistics.mean(durations), 2),
            "min_ms": round(min(durations), 2),
            "max_ms": round(max(durations), 2),
            "p95_ms": round(sorted_d[p95_idx], 2),
        }
    else:
        latency = {"avg_ms": 0, "min_ms": 0, "max_ms": 0, "p95_ms": 0}

    # Per-workflow breakdown
    per_workflow: dict[str, dict[str, Any]] = {}
    for run in all_runs:
        wf_id = run.workflow_id
        if wf_id not in per_workflow:
            per_workflow[wf_id] = {"runs": 0, "completed": 0, "failed": 0, "durations": []}
        per_workflow[wf_id]["runs"] += 1
        if run.status.value == "completed":
            per_workflow[wf_id]["completed"] += 1
        elif run.status.value == "failed":
            per_workflow[wf_id]["failed"] += 1
        d = _run_duration_ms(run)
        if d is not None:
            per_workflow[wf_id]["durations"].append(d)

    per_workflow_out: dict[str, dict[str, Any]] = {}
    for wf_id, data in per_workflow.items():
        avg_lat = round(statistics.mean(data["durations"]), 2) if data["durations"] else 0
        per_workflow_out[wf_id] = {
            "runs": data["runs"],
            "completed": data["completed"],
            "failed": data["failed"],
            "avg_latency_ms": avg_lat,
        }

    # Recent runs (last 20, newest first)
    recent = sorted(all_runs, key=lambda r: r.started_at, reverse=True)[:20]
    recent_out = []
    for r in recent:
        recent_out.append({
            "run_id": r.run_id,
            "workflow_id": r.workflow_id,
            "status": r.status.value,
            "duration_ms": _run_duration_ms(r),
            "node_count": len(r.node_runs),
            "started_at": r.started_at,
        })

    return {
        "totals": {
            "workflows": len(_workflows),
            "runs": _metrics["runs_total"],
            "nodes_succeeded": _metrics["nodes_succeeded"],
            "nodes_failed": _metrics["nodes_failed"],
            "retries": _metrics["retries_total"],
        },
        "runs": {
            "completed": len(completed),
            "failed": len(failed),
            "success_rate": round(success_rate, 1),
        },
        "latency": latency,
        "per_workflow": per_workflow_out,
        "recent_runs": recent_out,
    }


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
