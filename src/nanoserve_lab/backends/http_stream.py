"""UTF-8/SSE framing and OpenAI-compatible single-choice delta normalization."""

import codecs
import json
import time
from collections.abc import AsyncIterator

import httpx

from ..schemas import RequestSpec, StreamEvent, valid_finish_reason
from .protocol import ProtocolError


async def sse_data(chunks: AsyncIterator[bytes]) -> AsyncIterator[str]:
    """Parse SSE lines, including fragmented UTF-8, CR/LF, comments and multiline data.

    A trailing event without the SSE blank-line delimiter is rejected rather than fabricated.
    """
    decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
    buffer = ""
    data: list[str] = []
    try:
        async for chunk in chunks:
            buffer += decoder.decode(chunk)
            if len(buffer) + sum(map(len, data)) > 8 * 1024 * 1024:
                raise ProtocolError("SSE event exceeds 8 MiB safety bound")
            while True:
                positions = [p for p in (buffer.find("\r"), buffer.find("\n")) if p >= 0]
                if not positions:
                    break
                position = min(positions)
                if buffer[position] == "\r" and position == len(buffer) - 1:
                    break
                line = buffer[:position]
                width = 2 if buffer[position : position + 2] == "\r\n" else 1
                buffer = buffer[position + width :]
                if not line:
                    if data:
                        yield "\n".join(data)
                        data = []
                elif line.startswith("data:"):
                    value = line[5:]
                    data.append(value[1:] if value.startswith(" ") else value)
        buffer += decoder.decode(b"", final=True)
    except UnicodeDecodeError as exc:
        raise ProtocolError("invalid UTF-8 in SSE stream") from exc
    # A final bare CR can terminate a blank line, per SSE line-ending rules.
    if buffer == "\r":
        if data:
            yield "\n".join(data)
        buffer, data = "", []
    if buffer or data:
        raise ProtocolError("unterminated SSE event at EOF")


class HTTPStreamBackend:
    def __init__(self, client: httpx.AsyncClient, endpoint: str):
        self.client, self.endpoint = client, endpoint

    async def stream(self, request: RequestSpec) -> AsyncIterator[StreamEvent]:
        start = time.monotonic()
        done = False
        finished = False
        usage_seen = False
        async with self.client.stream("POST", self.endpoint, json=request.body) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "text/event-stream" not in content_type:
                raise ProtocolError(f"expected text/event-stream, got {content_type!r}")
            async for payload in sse_data(response.aiter_bytes()):
                if done:
                    raise ProtocolError("data after [DONE]")
                if payload == "[DONE]":
                    done = True
                    yield StreamEvent(kind="done", elapsed_s=time.monotonic() - start)
                    continue
                try:

                    def reject_nonfinite(value):
                        raise ValueError(f"non-finite JSON constant: {value}")

                    item = json.loads(payload, parse_constant=reject_nonfinite)
                except ValueError as exc:
                    raise ProtocolError("invalid JSON in SSE data") from exc
                if not isinstance(item, dict) or item.get("error"):
                    raise ProtocolError(f"server error or invalid object: {item}")
                choices = item.get("choices", [])
                if not isinstance(choices, list) or len(choices) > 1:
                    raise ProtocolError("only single-choice streams are supported")
                for choice in choices:
                    if not isinstance(choice, dict) or choice.get("index", 0) != 0:
                        raise ProtocolError("unsupported choice index")
                    delta = choice.get("delta", {})
                    if not isinstance(delta, dict):
                        raise ProtocolError("delta must be an object")
                    if finished and any(value for value in delta.values()):
                        raise ProtocolError("content after finish_reason")
                    unsupported = set(delta) - {
                        "role",
                        "content",
                        "reasoning_content",
                        "reasoning",
                        "tool_calls",
                        "refusal",
                    }
                    if unsupported:
                        raise ProtocolError(f"unsupported delta fields: {sorted(unsupported)}")
                    for key, kind in [
                        ("role", "role"),
                        ("content", "text"),
                        ("reasoning_content", "reasoning"),
                        ("reasoning", "reasoning"),
                        ("refusal", "refusal"),
                    ]:
                        value = delta.get(key)
                        if value is not None and not isinstance(value, str):
                            raise ProtocolError(f"delta.{key} must be text")
                        if value:
                            yield StreamEvent(
                                kind=kind, elapsed_s=time.monotonic() - start, data=value
                            )
                    tool_calls = delta.get("tool_calls", [])
                    if not isinstance(tool_calls, list):
                        raise ProtocolError("tool_calls must be an array")
                    for tool in tool_calls:
                        try:
                            arguments = tool.get("function", {}).get("arguments")
                        except AttributeError as exc:
                            raise ProtocolError("invalid tool delta") from exc
                        if arguments is not None and not isinstance(arguments, str):
                            raise ProtocolError("tool arguments must be text")
                        if arguments:
                            yield StreamEvent(
                                kind="tool_arguments",
                                elapsed_s=time.monotonic() - start,
                                data=arguments,
                            )
                        else:
                            yield StreamEvent(
                                kind="tool_metadata", elapsed_s=time.monotonic() - start, data=tool
                            )
                    if choice.get("finish_reason") is not None:
                        if finished or not valid_finish_reason(choice["finish_reason"]):
                            raise ProtocolError("duplicate or invalid finish_reason")
                        finished = True
                        yield StreamEvent(
                            kind="finish",
                            elapsed_s=time.monotonic() - start,
                            data=choice["finish_reason"],
                        )
                if item.get("usage") is not None:
                    if usage_seen or not isinstance(item["usage"], dict):
                        raise ProtocolError("duplicate or invalid usage")
                    usage_seen = True
                    yield StreamEvent(
                        kind="usage", elapsed_s=time.monotonic() - start, data=item["usage"]
                    )
        if not done:
            raise ProtocolError("stream ended without [DONE]")
