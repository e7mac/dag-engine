# DAG Workflow Engine

An async DAG workflow engine in Python for orchestrating third-party API calls with branching logic, retry with exponential backoff, and a REST API.

## Setup

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run the API server
uvicorn src.main:app --reload

# Run tests
pytest tests/ -v
```

## Architecture

```
src/
├── types.py                 # Pydantic models: WorkflowDef, NodeDef, WorkflowRun, etc.
├── engine/
│   ├── executor.py          # Core DAG walker — executes workflows from start to end
│   ├── scheduler.py         # Path analysis utilities for concurrent execution
│   ├── retry.py             # Generic async retry with exponential backoff
│   └── nodes/
│       ├── base.py          # Dot-notation resolver + {{context.x}} template engine
│       ├── third_party.py   # HTTP node executor (httpx + mock/sandbox support)
│       └── branch.py        # Conditional branching with 5 operators
├── validation/
│   └── dag_validator.py     # Pre-execution DAG validation (cycles, reachability, termination)
├── store/
│   └── run_store.py         # In-memory run storage + optional JSON file persistence
└── api/
    └── server.py            # FastAPI REST API
```

### How it works

1. **Register** a workflow definition (JSON DAG of nodes)
2. **Validate** the DAG — checks for cycles, unreachable nodes, dead ends, and non-terminating paths
3. **Execute** — the engine walks from `start_node_id`, dispatching each node:
   - **third_party**: makes an HTTP call (or returns mock data in sandbox mode), writes response to `context["nodes"][node_id]["response"]`
   - **branch**: evaluates conditions against context, picks the first matching edge
   - **end**: terminates the path
4. **Retry** — failed HTTP calls retry with exponential backoff (`backoff_ms * 2^(attempt-1)`)
5. **Context** — a shared dict threaded through all nodes; templates like `{{context.sku}}` resolve at execution time

### Node types

| Type | Description |
|------|-------------|
| `third_party` | HTTP call via httpx. Supports GET/POST/PUT/PATCH/DELETE, timeout, retry config, and mock responses. |
| `branch` | Evaluates edges in order using operators: `equals`, `contains`, `gt`, `lt`, `exists`. Falls back to `default_next`. |
| `end` | Terminal node. Marks the path as complete. |

## Sandbox mode vs Live mode

- **Sandbox mode** (`sandbox_mode: true`): No real HTTP calls. Uses `mock.body` from each node's config. Use for testing workflows.
- **Live mode** (`sandbox_mode: false`): Makes real HTTP calls via httpx with retry and timeout.

## API Reference

### Register a workflow
```bash
curl -X POST http://localhost:8000/workflows \
  -H "Content-Type: application/json" \
  -d @examples/order_fulfillment.json
```

### Get a workflow
```bash
curl http://localhost:8000/workflows/order-fulfillment
```

### Validate a workflow
```bash
curl -X POST http://localhost:8000/workflows/order-fulfillment/validate
```

### Run a workflow (sandbox)
```bash
curl -X POST http://localhost:8000/workflows/order-fulfillment/run \
  -H "Content-Type: application/json" \
  -d '{"initial_context": {"sku": "WIDGET-001"}, "sandbox_mode": true}'
```

Returns `{"run_id": "..."}`. The workflow executes in the background.

### Poll run status
```bash
curl http://localhost:8000/runs/<run_id>
```

### Get execution trace
```bash
curl http://localhost:8000/runs/<run_id>/trace
```

Returns `execution_path` with per-node timing (`started_at`, `completed_at`, `duration_ms`, `attempts`).

### Metrics
```bash
curl http://localhost:8000/metrics
```

Prometheus-compatible counters: `runs_total`, `nodes_succeeded`, `nodes_failed`, `retries_total`.

## Persistence

Set `PERSIST_RUNS=true` to write each completed run to `runs/{run_id}.json`:

```bash
PERSIST_RUNS=true uvicorn src.main:app
```

## Tradeoffs and future work

**What's here:**
- Fully async execution with httpx
- Exponential backoff retry with configurable attempts
- Template resolution for URLs and request bodies
- DAG validation (cycles, reachability, termination, dead ends)
- Sandbox mode for testing without real HTTP calls
- Structured logging with per-node timing
- Prometheus-compatible metrics endpoint

**What you'd add with more time:**
- **Workflow versioning** — store multiple versions, diff between them, roll back
- **Persistent DB** — replace in-memory dict with PostgreSQL/SQLite for durable storage
- **SSE streaming** — stream run status updates instead of polling
- **Rate limiting** — per-node or per-domain rate limits on third-party calls
- **Parallel path execution** — detect independent branches after a split and run them via `asyncio.gather`
- **Webhook callbacks** — notify external systems on run completion/failure
- **DAG visualization** — generate Mermaid/Graphviz diagrams from workflow definitions
- **Node-level timeouts** — per-workflow timeout in addition to per-node HTTP timeouts
