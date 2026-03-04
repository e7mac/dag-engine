from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from src.engine.nodes.base import resolve_template
from src.engine.retry import with_retry
from src.types import NodeRun, NodeStatus, ThirdPartyNodeDef

logger = logging.getLogger(__name__)


async def execute_third_party(
    node_def: ThirdPartyNodeDef,
    context: dict[str, Any],
    sandbox_mode: bool = False,
) -> NodeRun:
    """Execute a third-party HTTP node."""
    node_run = NodeRun(node_id=node_def.id)
    node_run.status = NodeStatus.RUNNING
    node_run.started_at = datetime.now(timezone.utc).isoformat()

    config = node_def.config

    # Resolve templates in url and body
    resolved_url = resolve_template(config.url, context)
    resolved_body = resolve_template(config.body, context) if config.body is not None else None
    resolved_headers = resolve_template(config.headers, context) if config.headers else {}

    node_run.input = {"url": resolved_url, "method": config.method, "body": resolved_body}

    if sandbox_mode and config.mock:
        # Sandbox mode: return mock response
        if config.mock.delay_ms > 0:
            await asyncio.sleep(config.mock.delay_ms / 1000.0)
        output = {"status": config.mock.status, "body": config.mock.body}
        node_run.output = output
        node_run.status = NodeStatus.SUCCESS
        node_run.attempts = 1
        node_run.completed_at = datetime.now(timezone.utc).isoformat()
        context.setdefault("nodes", {})
        context["nodes"][node_def.id] = {"response": config.mock.body}
        logger.info(
            "node_completed",
            extra={"node_id": node_def.id, "status": "success", "attempts": 1, "sandbox": True},
        )
        return node_run

    # Real HTTP execution with retry
    attempt_count = 0

    async def make_request() -> dict[str, Any]:
        nonlocal attempt_count
        attempt_count += 1
        timeout = httpx.Timeout(config.timeout_ms / 1000.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=config.method,
                url=resolved_url,
                headers=resolved_headers,
                json=resolved_body if resolved_body is not None else None,
            )
            response.raise_for_status()
            try:
                body = response.json()
            except Exception:
                body = response.text
            return {"status": response.status_code, "body": body}

    def on_attempt(attempt: int, exc: Exception) -> None:
        logger.warning(
            "node_retry",
            extra={"node_id": node_def.id, "attempt": attempt, "error": str(exc)},
        )

    try:
        result = await with_retry(make_request, config.retry, on_attempt=on_attempt)
        node_run.output = result
        node_run.status = NodeStatus.SUCCESS
        node_run.attempts = attempt_count
        context.setdefault("nodes", {})
        context["nodes"][node_def.id] = {"response": result["body"]}
        logger.info(
            "node_completed",
            extra={"node_id": node_def.id, "status": "success", "attempts": attempt_count},
        )
    except Exception as exc:
        node_run.status = NodeStatus.FAILED
        node_run.error = str(exc)
        node_run.attempts = attempt_count
        logger.error(
            "node_failed",
            extra={"node_id": node_def.id, "status": "failed", "attempts": attempt_count, "error": str(exc)},
        )

    node_run.completed_at = datetime.now(timezone.utc).isoformat()
    return node_run
