from __future__ import annotations

import logging

from src.types import BranchNodeDef, EndNodeDef, NodeId, ThirdPartyNodeDef, WorkflowDef

logger = logging.getLogger(__name__)


def validate_workflow(workflow: WorkflowDef) -> list[str]:
    """Validate a workflow definition. Returns list of error strings. Empty = valid."""
    errors: list[str] = []

    # 1. Start node exists
    if workflow.start_node_id not in workflow.nodes:
        errors.append(f"start_node_id '{workflow.start_node_id}' not found in nodes")
        return errors  # Can't continue without a valid start node

    # 2. Dead ends — every non-end node must have valid next/edges pointing to existing node IDs
    for node_id, node_def in workflow.nodes.items():
        if isinstance(node_def, ThirdPartyNodeDef):
            if node_def.next not in workflow.nodes:
                errors.append(f"Node '{node_id}' has next '{node_def.next}' which does not exist")
        elif isinstance(node_def, BranchNodeDef):
            for edge in node_def.edges:
                if edge.next not in workflow.nodes:
                    errors.append(
                        f"Branch node '{node_id}' edge '{edge.label}' points to "
                        f"'{edge.next}' which does not exist"
                    )
            if node_def.default_next and node_def.default_next not in workflow.nodes:
                errors.append(
                    f"Branch node '{node_id}' default_next '{node_def.default_next}' does not exist"
                )
            # Warn if branch has no default_next
            if not node_def.default_next:
                logger.warning(
                    "Branch node '%s' has no default_next — may fail at runtime if no edge matches",
                    node_id,
                )

    # 3. Reachability — every node must be reachable from start_node_id
    reachable = _find_reachable(workflow)
    for node_id in workflow.nodes:
        if node_id not in reachable:
            errors.append(f"Node '{node_id}' is not reachable from start_node_id '{workflow.start_node_id}'")

    # 4. Cycle detection — DFS from start_node_id
    cycle = _detect_cycle(workflow)
    if cycle:
        errors.append(f"Cycle detected: {' -> '.join(cycle)}")

    # 5. All paths terminate — every branch edge and default_next must eventually reach an end node
    if not errors:  # Only check if no structural errors so far
        termination_errors = _check_all_paths_terminate(workflow)
        errors.extend(termination_errors)

    return errors


def _find_reachable(workflow: WorkflowDef) -> set[NodeId]:
    """BFS/DFS to find all nodes reachable from start_node_id."""
    reachable: set[NodeId] = set()
    stack = [workflow.start_node_id]

    while stack:
        node_id = stack.pop()
        if node_id in reachable:
            continue
        if node_id not in workflow.nodes:
            continue
        reachable.add(node_id)

        node_def = workflow.nodes[node_id]
        if isinstance(node_def, ThirdPartyNodeDef):
            stack.append(node_def.next)
        elif isinstance(node_def, BranchNodeDef):
            for edge in node_def.edges:
                stack.append(edge.next)
            if node_def.default_next:
                stack.append(node_def.default_next)

    return reachable


def _detect_cycle(workflow: WorkflowDef) -> list[NodeId] | None:
    """DFS cycle detection from start_node_id. Returns the cycle path if found."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[NodeId, int] = {nid: WHITE for nid in workflow.nodes}
    parent: dict[NodeId, NodeId | None] = {}

    def _get_successors(node_id: NodeId) -> list[NodeId]:
        node_def = workflow.nodes.get(node_id)
        if node_def is None:
            return []
        if isinstance(node_def, ThirdPartyNodeDef):
            return [node_def.next]
        elif isinstance(node_def, BranchNodeDef):
            succs = [edge.next for edge in node_def.edges]
            if node_def.default_next:
                succs.append(node_def.default_next)
            return succs
        return []

    def dfs(node_id: NodeId) -> list[NodeId] | None:
        color[node_id] = GRAY
        for succ in _get_successors(node_id):
            if succ not in color:
                continue
            if color[succ] == GRAY:
                # Found a back-edge → reconstruct cycle
                cycle = [succ, node_id]
                current = node_id
                while current != succ:
                    current = parent.get(current)  # type: ignore[assignment]
                    if current is None:
                        break
                    cycle.append(current)
                cycle.reverse()
                return cycle
            if color[succ] == WHITE:
                parent[succ] = node_id
                result = dfs(succ)
                if result:
                    return result
        color[node_id] = BLACK
        return None

    parent[workflow.start_node_id] = None
    return dfs(workflow.start_node_id)


def _check_all_paths_terminate(workflow: WorkflowDef) -> list[str]:
    """Check that every path from start eventually reaches an end node."""
    errors: list[str] = []
    memo: dict[NodeId, bool] = {}

    def reaches_end(node_id: NodeId, visited: set[NodeId]) -> bool:
        if node_id in memo:
            return memo[node_id]
        if node_id in visited:
            return False  # Cycle, shouldn't happen if cycle check passed
        if node_id not in workflow.nodes:
            return False

        visited = visited | {node_id}
        node_def = workflow.nodes[node_id]

        if isinstance(node_def, EndNodeDef):
            memo[node_id] = True
            return True
        elif isinstance(node_def, ThirdPartyNodeDef):
            result = reaches_end(node_def.next, visited)
            memo[node_id] = result
            return result
        elif isinstance(node_def, BranchNodeDef):
            all_reach = True
            for edge in node_def.edges:
                if not reaches_end(edge.next, visited):
                    errors.append(
                        f"Branch node '{node_id}' edge '{edge.label}' path does not reach an end node"
                    )
                    all_reach = False
            if node_def.default_next and not reaches_end(node_def.default_next, visited):
                errors.append(
                    f"Branch node '{node_id}' default_next path does not reach an end node"
                )
                all_reach = False
            memo[node_id] = all_reach
            return all_reach

        return False

    reaches_end(workflow.start_node_id, set())
    return errors
