import asyncio

import pytest

from nanoserve_lab.backends.fixture import FixtureBackend
from nanoserve_lab.backends.protocol import ProtocolError
from nanoserve_lab.runner import run_requests
from nanoserve_lab.schemas import RunConfig, StreamEvent
from nanoserve_lab.workloads import build_requests


async def test_concurrency_bound_and_all_results():
    class Tracking(FixtureBackend):
        active = 0
        maximum = 0

        async def stream(self, request):
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            try:
                async for event in super().stream(request):
                    yield event
            finally:
                self.active -= 1

    config = RunConfig(request_count=15, concurrency=3)
    backend = Tracking(0.002)
    results = await run_requests(config, backend, build_requests(config))
    assert len(results) == 15
    assert all(r.complete for r in results)
    assert backend.maximum == 3
    assert backend.active == 0


async def test_timeout_preserves_partial_output_and_no_retry():
    class Slow(FixtureBackend):
        calls = 0

        async def stream(self, request):
            self.calls += 1
            yield StreamEvent(kind="text", elapsed_s=0, data="partial")
            await asyncio.sleep(10)

    config = RunConfig(request_count=2, concurrency=1, timeout_s=0.04)
    backend = Slow(0)
    results = await run_requests(config, backend, build_requests(config))
    assert [r.status for r in results] == ["timeout", "timeout"]
    assert backend.calls == 2
    assert all(r.text and r.text_tpot_proxy_s is None for r in results)


async def test_protocol_failure_remains_in_results():
    class Broken(FixtureBackend):
        async def stream(self, request):
            async for event in super().stream(request):
                yield event
                raise ProtocolError("broken")

    config = RunConfig(request_count=2)
    results = await run_requests(config, Broken(), build_requests(config))
    assert all(r.status == "protocol_error" and r.error == "broken" for r in results)


async def test_client_cancellation_records_active_and_not_unsent():
    config = RunConfig(request_count=20, concurrency=2)
    saved = []
    task = asyncio.create_task(
        run_requests(config, FixtureBackend(1), build_requests(config), saved.append)
    )
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(saved) == 2
    assert all(r.status == "cancelled" for r in saved)
