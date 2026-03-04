from __future__ import annotations

import json
import os
from pathlib import Path

from src.types import WorkflowRun


class RunStore:
    def __init__(self) -> None:
        self._runs: dict[str, WorkflowRun] = {}
        self._persist = os.environ.get("PERSIST_RUNS", "").lower() == "true"
        if self._persist:
            self._runs_dir = Path("runs")
            self._runs_dir.mkdir(exist_ok=True)

    def save(self, run: WorkflowRun) -> None:
        self._runs[run.run_id] = run
        if self._persist:
            path = self._runs_dir / f"{run.run_id}.json"
            path.write_text(run.model_dump_json(indent=2))

    def get(self, run_id: str) -> WorkflowRun | None:
        return self._runs.get(run_id)

    def list_runs(self, workflow_id: str | None = None) -> list[WorkflowRun]:
        runs = list(self._runs.values())
        if workflow_id:
            runs = [r for r in runs if r.workflow_id == workflow_id]
        return runs
