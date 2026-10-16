"""Closed-loop bounded concurrency; every sent request produces a durable result."""

import asyncio
import time
from collections.abc import Callable

import httpx

from .backends.protocol import Backend, ProtocolError
from .metrics import reduce_events
from .schemas import RequestResult, RequestSpec, RunConfig


async def run_requests(
    config: RunConfig,
    backend: Backend,
    requests: list[RequestSpec],
    on_result: Callable[[RequestResult], None] | None = None,
) -> list[RequestResult]:
    origin = time.monotonic()
    iterator = iter(requests)
    results: list[RequestResult] = []

    async def worker():
        for request in iterator:
            events = []
            sent = time.monotonic() - origin
            status, error = "succeeded", None
            cancelled = False
            try:
                async with asyncio.timeout(config.timeout_s):
                    async for event in backend.stream(request):
                        events.append(event)
            except (TimeoutError, httpx.TimeoutException) as exc:
                status, error = "timeout", f"{type(exc).__name__}: request timeout"
            except httpx.HTTPStatusError as exc:
                status, error = "http_error", f"HTTP {exc.response.status_code}"
            except ProtocolError as exc:
                status, error = "protocol_error", str(exc)
            except asyncio.CancelledError:
                status, error, cancelled = "cancelled", "client cancellation", True
            except (
                Exception
            ) as exc:  # Preserve unknown failures without inventing an OOM diagnosis.
                status, error = "error", f"{type(exc).__name__}: {exc}"
            ended = time.monotonic() - origin
            scope = "text" if config.backend == "fixture" else config.usage_token_scope
            result = reduce_events(request.request_id, events, sent, ended, status, error, scope)
            results.append(result)
            if on_result:
                on_result(result)
            if cancelled:
                raise asyncio.CancelledError

    workers = [asyncio.create_task(worker()) for _ in range(min(config.concurrency, len(requests)))]
    try:
        await asyncio.gather(*workers)
    finally:
        for task in workers:
            if not task.done():
                task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
    return sorted(results, key=lambda result: result.request_id)
