from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field

NodeId = str


class RetryConfig(BaseModel):
    max_attempts: int = 3
    backoff_ms: int = 1000


class MockConfig(BaseModel):
    status: int
    body: Any
    delay_ms: int = 0


class ThirdPartyConfig(BaseModel):
    url: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    headers: dict[str, str] = {}
    body: Any = None
    timeout_ms: int = 10_000
    retry: RetryConfig = Field(default_factory=RetryConfig)
    mock: MockConfig | None = None


class ThirdPartyNodeDef(BaseModel):
    id: NodeId
    type: Literal["third_party"]
    label: str
    config: ThirdPartyConfig
    next: NodeId


class Operator(str, Enum):
    EQUALS = "equals"
    CONTAINS = "contains"
    GT = "gt"
    LT = "lt"
    EXISTS = "exists"


class BranchCondition(BaseModel):
    field: str
    operator: Operator
    value: Any = None


class BranchEdge(BaseModel):
    label: str
    condition: BranchCondition
    next: NodeId


class BranchNodeDef(BaseModel):
    id: NodeId
    type: Literal["branch"]
    label: str
    edges: list[BranchEdge]
    default_next: NodeId | None = None
    concurrent: bool = False


class EndNodeDef(BaseModel):
    id: NodeId
    type: Literal["end"]
    label: str


NodeDef = Annotated[
    Union[ThirdPartyNodeDef, BranchNodeDef, EndNodeDef],
    Field(discriminator="type"),
]


class WorkflowDef(BaseModel):
    id: str
    name: str
    version: int = 1
    start_node_id: NodeId
    nodes: dict[NodeId, NodeDef]


class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class NodeRun(BaseModel):
    node_id: NodeId
    status: NodeStatus = NodeStatus.PENDING
    started_at: str | None = None
    completed_at: str | None = None
    input: Any = None
    output: Any = None
    error: str | None = None
    attempts: int = 0
    branch_taken: str | None = None


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowRun(BaseModel):
    run_id: str
    workflow_id: str
    status: RunStatus = RunStatus.PENDING
    started_at: str
    completed_at: str | None = None
    context: dict[str, Any] = {}
    node_runs: dict[NodeId, NodeRun] = {}
    execution_path: list[NodeId] = []
    sandbox_mode: bool = False
