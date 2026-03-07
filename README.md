# DAG Workflow Engine

An async DAG workflow engine in Python for orchestrating third-party API calls with branching logic, retry with exponential backoff, and a web dashboard.

## Setup

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run the API server
uvicorn src.main:app --reload

# Run tests
pytest tests/ -v
```

Open `http://localhost:8000` for the dashboard.

## Quick start — run a workflow from the dashboard

1. Start the server: `uvicorn src.main:app --reload`
2. Open `http://localhost:8000` in your browser
3. Click **Load User Lookup** in the header bar
4. The DAG canvas shows the workflow graph; the sidebar selects it automatically
5. The context editor (right panel) pre-fills with `{"user_id": 4}`
6. Click **Run Live** in the toolbar — this makes real HTTP calls to JSONPlaceholder
7. The run appears in the sidebar; once it finishes, the trace panel shows each node's status, timing, and response data
8. Hover over a trace node to highlight it on the DAG canvas

## Architecture

```
src/
├── types.py                 # Pydantic models: WorkflowDef, NodeDef, WorkflowRun, etc.
├── main.py                  # Entrypoint — uvicorn on :8000
├── engine/
│   ├── executor.py          # Core DAG walker — executes workflows from start to end
│   ├── scheduler.py         # Static graph analysis (successor/path tracing)
│   ├── retry.py             # Generic async retry with exponential backoff
│   └── nodes/
│       ├── base.py          # Dot-notation resolver + {{context.x}} template engine
│       ├── third_party.py   # HTTP node executor (httpx + mock/sandbox support)
│       └── branch.py        # Conditional branching with 5 operators
├── validation/
│   └── dag_validator.py     # Pre-execution DAG validation (cycles, reachability, termination)
├── store/
│   └── run_store.py         # In-memory run storage + optional JSON file persistence
├── api/
│   └── server.py            # FastAPI REST API + metrics + stats
└── static/
    ├── index.html           # HTML shell — structure + script/link tags
    ├── styles.css           # All CSS with section comments
    └── js/
        ├── state.js         # State object + EXAMPLES data
        ├── api.js           # HTTP layer (fetch, fetchWorkflows, fetchRuns, fetchStats)
        ├── ui.js            # Toast, escape, modals, toggleDetail, toggleStats
        ├── sidebar.js       # Workflow list, run list, selectWorkflow, selectRun
        ├── workflow.js      # Register, validate, loadExample, context helpers
        ├── runner.js        # Execute, poll, resume
        ├── trace.js         # Render trace, clear, renderStats
        ├── dag.js           # Canvas DAG rendering
        └── init.js          # Window resize handler + startup fetches
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
| `branch` | Evaluates edges in order (first match wins) using operators: `equals`, `contains`, `gt`, `lt`, `exists`. Falls back to `default_next`. |
| `end` | Terminal node. Marks the path as complete. |

### Template engine

URLs and request bodies support `{{context.path}}` placeholders:

```json
{
  "url": "https://api.example.com/users/{{context.user_id}}",
  "body": { "key": "{{context.api_key}}" }
}
```

- Dot-path resolution traverses nested dicts and lists (e.g. `nodes.fetch.response.items.0.id`)
- Full-string placeholders like `"{{context.count}}"` preserve the original type (int, bool, etc.)
- Partial-string placeholders stringify: `"Hello {{context.name}}"` → `"Hello Alice"`

### DAG validation

`validate_workflow()` runs 5 checks before every execution:

1. Start node exists in the node map
2. All `next` / edge targets point to existing node IDs
3. All nodes are reachable from `start_node_id` (BFS)
4. No cycles (DFS with gray/white/black coloring)
5. All paths terminate at an end node (recursive memoized check)

## Dashboard

The web dashboard at `http://localhost:8000` is a set of static files (no build step). Features:

- **Workflow list** — sidebar showing registered workflows
- **DAG canvas** — visual graph drawn on `<canvas>` with topological layering; edges highlight blue when taken during a run
- **Run management** — trigger runs (sandbox or live), view run list with status badges
- **Execution trace** — vertical timeline per node showing status, duration, start timestamp; expandable details with full input/output/error/timing JSON
- **Hover highlighting** — hovering a trace node highlights it on the DAG canvas with a blue glow
- **Example workflows** — 5 built-in examples loadable via buttons (Order Fulfillment, Email Validation, User Lookup, Fault Tolerance, Resume Test)
- **Stats panel** — toggleable overlay with run counts, success rates, latency percentiles, per-workflow breakdown

## Sandbox mode vs Live mode

- **Sandbox** (`sandbox_mode: true`): no real HTTP calls. Uses `mock.body` from each node's config. Use for testing workflows without external dependencies.
- **Live** (`sandbox_mode: false`): makes real HTTP calls via httpx with retry and timeout.

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/workflows` | Register (or overwrite) a workflow definition |
| `GET` | `/workflows` | List all registered workflows |
| `GET` | `/workflows/{id}` | Get a workflow definition |
| `POST` | `/workflows/{id}/validate` | Run DAG validation |
| `POST` | `/workflows/{id}/run` | Execute workflow in background |
| `GET` | `/runs` | List runs (filter with `?workflow_id=`) |
| `GET` | `/runs/{id}` | Get full run data |
| `GET` | `/runs/{id}/trace` | Get execution trace with per-node timing |
| `GET` | `/stats` | Aggregated stats (success rate, latency, per-workflow) |
| `GET` | `/metrics` | Prometheus-compatible counters |
| `GET` | `/test/flaky?fail_count=N` | Test endpoint that fails N times then succeeds |

### Examples

```bash
# Register a workflow
curl -X POST http://localhost:8000/workflows \
  -H "Content-Type: application/json" \
  -d @examples/order_fulfillment.json

# Run in sandbox mode
curl -X POST http://localhost:8000/workflows/order-fulfillment/run \
  -H "Content-Type: application/json" \
  -d '{"initial_context": {"sku": "WIDGET-001"}, "sandbox_mode": true}'

# Poll run status
curl http://localhost:8000/runs/<run_id>

# Get execution trace
curl http://localhost:8000/runs/<run_id>/trace
```

## Example workflows

| Example | File | Description |
|---------|------|-------------|
| Order Fulfillment | `examples/order_fulfillment.json` | Check inventory → branch on stock → create shipment or cancel |
| Email Validation | `examples/email_validation.json` | Validate email → check IP risk → route by risk level (low/medium/high) |
| User Lookup | `examples/user_lookup.json` | Fetch user + posts from JSONPlaceholder → branch on activity |
| Fault Tolerance | `examples/fault_tolerance.json` | Hit a flaky endpoint that fails 2x then recovers (tests retry) |
| Resume Test | `examples/resume_test.json` | Fetch user → flaky enrichment → branch on tier → fetch rewards (tests resume from failure) |

## Persistence

Run data is in-memory by default. Set `PERSIST_RUNS=true` to write each completed run as JSON:

```bash
PERSIST_RUNS=true uvicorn src.main:app
```

Writes to `runs/{run_id}.json`. Note: these are not reloaded on restart (write-only audit log). Workflow definitions are always in-memory and lost on restart.

## Tests

45 tests across 4 files:

| File | Count | Covers |
|------|-------|--------|
| `test_branch.py` | 17 | All operators, dot-path resolution, first-match semantics |
| `test_executor.py` | 10 | Happy path, branching, sandbox mocks, context passing, example workflows, resume |
| `test_retry.py` | 6 | Immediate success, retry on Nth attempt, exhaustion, callback, backoff timing |
| `test_validation.py` | 12 | Missing start node, broken refs, unreachable nodes, cycles, unterminated paths, templates |

```bash
pytest tests/ -v
```

## Tradeoffs and future work

**What's here:**
- Fully async execution with httpx
- Exponential backoff retry with configurable attempts
- Template resolution for URLs and request bodies
- DAG validation (cycles, reachability, termination, dead ends)
- Sandbox mode for testing without real HTTP calls
- Web dashboard with DAG visualization, execution traces, and hover highlighting
- Structured logging with per-node timing
- Prometheus-compatible metrics endpoint
- Aggregated stats with per-workflow breakdown

**What you'd add with more time:**
- **Fork / fan-out node** — a dedicated node type that runs all matching edges concurrently via `asyncio.gather` (separate from branch, which is first-match routing)
- **Join / fan-in node** — wait for all concurrent paths to complete before continuing
- **Workflow versioning** — store multiple versions, diff between them, roll back
- **Persistent DB** — replace in-memory dict with PostgreSQL/SQLite for durable storage
- **SSE streaming** — stream run status updates instead of polling
- **Rate limiting** — per-node or per-domain rate limits on third-party calls
- **Webhook callbacks** — notify external systems on run completion/failure
- **Node-level timeouts** — per-workflow timeout in addition to per-node HTTP timeouts
