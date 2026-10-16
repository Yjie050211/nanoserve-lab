"""Synthetic event generator for CPU correctness tests, never performance evidence."""

import asyncio
import time
from collections.abc import AsyncIterator

from ..schemas import RequestSpec, StreamEvent


class FixtureBackend:
    def __init__(self, delay_s: float = 0.001):
        self.delay_s = delay_s

    async def stream(self, request: RequestSpec) -> AsyncIterator[StreamEvent]:
        start = time.monotonic()
        yield StreamEvent(kind="role", elapsed_s=time.monotonic() - start, data="assistant")
        for word in ["synthetic", " fixture", " output"]:
            await asyncio.sleep(self.delay_s)
            yield StreamEvent(kind="text", elapsed_s=time.monotonic() - start, data=word)
        yield StreamEvent(kind="finish", elapsed_s=time.monotonic() - start, data="stop")
        yield StreamEvent(
            kind="usage",
            elapsed_s=time.monotonic() - start,
            data={"completion_tokens": 3, "prompt_tokens": 1},
        )
        yield StreamEvent(kind="done", elapsed_s=time.monotonic() - start)
