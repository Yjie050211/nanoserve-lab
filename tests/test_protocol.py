import json

import httpx
import pytest

from nanoserve_lab.backends.http_stream import HTTPStreamBackend, sse_data
from nanoserve_lab.backends.protocol import ProtocolError
from nanoserve_lab.metrics import reduce_events
from nanoserve_lab.runner import run_requests
from nanoserve_lab.schemas import RequestSpec, RunConfig
from nanoserve_lab.workloads import build_requests


async def chunks(parts):
    for part in parts:
        yield part


class BytesStream(httpx.AsyncByteStream):
    def __init__(self, data):
        self.data = data

    async def __aiter__(self):
        for i in range(len(self.data)):
            yield self.data[i : i + 1]


def frame(value):
    return "data: " + json.dumps(value, ensure_ascii=False) + "\r\n\r\n"


def completion(delta, finish=None):
    return {"choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


async def get_events(body, content_type="text/event-stream", status=200):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            status, stream=BytesStream(body.encode()), headers={"content-type": content_type}
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        return [
            e
            async for e in HTTPStreamBackend(client, "http://test/v1/chat/completions").stream(
                RequestSpec(request_id="r", body={"stream": True})
            )
        ]


async def test_utf8_byte_fragments_role_empty_usage_tool_reasoning():
    body = ": heartbeat\r\n\r\n" + frame(completion({"role": "assistant", "content": ""}))
    body += frame(completion({"reasoning_content": "思考"}))
    body += frame(completion({"content": "你好"}))
    body += frame(completion({"tool_calls": [{"function": {"name": "f"}}]}))
    body += frame(completion({"tool_calls": [{"function": {"arguments": "{}"}}]}))
    body += frame(completion({}, "stop"))
    body += frame({"choices": [], "usage": {"completion_tokens": 3}}) + "data: [DONE]\r\n\r\n"
    events = await get_events(body)
    assert [e.kind for e in events] == [
        "role",
        "reasoning",
        "text",
        "tool_metadata",
        "tool_arguments",
        "finish",
        "usage",
        "done",
    ]
    assert events[2].data == "你好"


async def test_sse_multiline_and_lf_comments():
    result = [x async for x in sse_data(chunks([b":comment\ndata: one\ndata: two\n\n"]))]
    assert result == ["one\ntwo"]


@pytest.mark.parametrize(
    "body",
    [
        "data: {broken}\n\n",
        "data: {}\n",
        "data: {}\n\n",
        "data: [DONE]\n\ndata: [DONE]\n\n",
        frame({"error": {"message": "failure"}}),
        frame({"choices": [{"index": 1, "delta": {}}]}),
        frame(completion({"content": ["bad"]})),
        frame(completion({"function_call": {"arguments": "{}"}})),
        frame(completion({}, "stop")) + frame(completion({"content": "late"})),
    ],
)
async def test_malformed_or_incomplete_http_200_fails(body):
    with pytest.raises(ProtocolError):
        await get_events(body)


async def test_wrong_content_type_and_http_error():
    with pytest.raises(ProtocolError):
        await get_events("{}", "application/json")
    with pytest.raises(httpx.HTTPStatusError):
        await get_events("failure", status=500)


async def test_invalid_utf8_fails():
    with pytest.raises(ProtocolError, match="UTF-8"):
        _ = [x async for x in sse_data(chunks([b"data: \xff\n\n"]))]


@pytest.mark.parametrize("reason", ["", " ", "future_unsupported", 123])
async def test_http_rejects_invalid_finish_reason(reason):
    body = frame(completion({}, reason)) + "data: [DONE]\n\n"
    with pytest.raises(ProtocolError, match="finish_reason"):
        await get_events(body)


@pytest.mark.parametrize(
    "reason", ["stop", "length", "tool_calls", "content_filter", "function_call"]
)
async def test_http_and_offline_agree_on_supported_finish_reasons(reason):
    body = frame(completion({"content": "x"}))
    body += frame(completion({}, reason)) + "data: [DONE]\n\n"
    events = await get_events(body)
    result = reduce_events(
        "r", events, 0, events[-1].elapsed_s + 0.001, "succeeded", None, "unknown"
    )
    assert result.complete and result.status == "succeeded"
    assert result.finish_reason == reason


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("success", "succeeded"),
        ("missing_finish", "protocol_error"),
        ("http_error", "http_error"),
        ("network_error", "error"),
        ("timeout", "timeout"),
    ],
)
async def test_http_backend_runner_integration(mode, expected):
    count = 0

    def handle(request):
        nonlocal count
        count += 1
        assert request.headers["content-type"] == "application/json"
        assert json.loads(request.content)["stream_options"]["include_usage"]
        if mode == "network_error":
            raise httpx.ConnectError("connection refused", request=request)
        if mode == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        body = frame(completion({"content": "hello"}))
        if mode != "missing_finish":
            body += frame(completion({}, "stop"))
        body += frame({"choices": [], "usage": {"completion_tokens": 2}})
        body += "data: [DONE]\n\n"
        return httpx.Response(
            500 if mode == "http_error" else 200,
            stream=BytesStream(body.encode()),
            headers={"content-type": "text/event-stream"},
        )

    config = RunConfig(backend="http", request_count=3, concurrency=2, usage_token_scope="text")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        results = await run_requests(
            config, HTTPStreamBackend(client, config.endpoint), build_requests(config)
        )
    assert count == 3  # no automatic retries
    assert len(results) == 3
    assert all(result.status == expected for result in results)
    if mode == "success":
        assert all(result.output_tokens == 2 and result.text == "hello" for result in results)
