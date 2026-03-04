from __future__ import annotations

from src.types import BranchNodeDef, EndNodeDef, NodeDef, NodeId, ThirdPartyNodeDef, WorkflowDef


def get_next_nodes(node_def: NodeDef, branch_result: NodeId | None = None) -> list[NodeId]:
    """Return the list of next node IDs for a given node.

    For branch nodes, if branch_result is provided, return that single target.
    Otherwise return all possible next nodes (used for validation/analysis).
    """
    if isinstance(node_def, ThirdPartyNodeDef):
        return [node_def.next]
    elif isinstance(node_def, BranchNodeDef):
        if branch_result is not None:
            return [branch_result]
        targets = [edge.next for edge in node_def.edges]
        if node_def.default_next:
            targets.append(node_def.default_next)
        return targets
    elif isinstance(node_def, EndNodeDef):
        return []
    return []


def find_concurrent_paths(workflow: WorkflowDef, branch_node_id: NodeId) -> list[list[NodeId]]:
    """Given a branch node, find independent paths that can run concurrently.

    Returns a list of paths, where each path is a list of node IDs starting
    from the branch target.
    """
    node_def = workflow.nodes[branch_node_id]
    if not isinstance(node_def, BranchNodeDef):
        return []

    paths: list[list[NodeId]] = []
    for edge in node_def.edges:
        path = _trace_linear_path(workflow, edge.next)
        paths.append(path)

    if node_def.default_next:
        path = _trace_linear_path(workflow, node_def.default_next)
        paths.append(path)

    return paths


def _trace_linear_path(workflow: WorkflowDef, start_id: NodeId) -> list[NodeId]:
    """Trace a linear path from a node until a branch or end is reached."""
    path: list[NodeId] = []
    current = start_id
    visited: set[NodeId] = set()

    while current and current not in visited:
        if current not in workflow.nodes:
            break
        visited.add(current)
        path.append(current)
        node = workflow.nodes[current]
        if isinstance(node, EndNodeDef):
            break
        if isinstance(node, BranchNodeDef):
            break
        if isinstance(node, ThirdPartyNodeDef):
            current = node.next
        else:
            break

    return path
