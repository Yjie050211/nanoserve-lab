"""Pure reductions from durable events; chunk count is never treated as token count."""

import math
from collections import Counter

from .schemas import RequestResult, StreamEvent, valid_finish_reason


def reduce_events(
    request_id: str,
    events: list[StreamEvent],
    sent_at_s: float,
    ended_at_s: float,
    status: str,
    error: str | None,
    usage_token_scope: str,
) -> RequestResult:
    times: dict[str, list[float]] = {"text": [], "tool_arguments": [], "reasoning": []}
    usage = None
    text, finish, protocol_end = "", None, None
    ordering_valid = True
    previous = -1.0
    done_count, finish_count = 0, 0
    for event in events:
        if done_count:
            ordering_valid = False
        if event.elapsed_s < previous or event.elapsed_s > ended_at_s - sent_at_s + 0.001:
            ordering_valid = False
        previous = event.elapsed_s
        if event.kind in times and isinstance(event.data, str) and event.data:
            if finish_count:
                ordering_valid = False
            times[event.kind].append(event.elapsed_s)
        if event.kind == "text" and isinstance(event.data, str):
            text += event.data
        elif event.kind == "usage":
            usage = event.data
        elif event.kind == "finish":
            finish_count += 1
            if not valid_finish_reason(event.data):
                ordering_valid = False
            finish = event.data if isinstance(event.data, str) else None
        elif event.kind == "done":
            protocol_end, done_count = event.elapsed_s, done_count + 1
    complete = status == "succeeded" and done_count == 1 and finish_count == 1 and ordering_valid
    if status == "succeeded" and not complete:
        status, error = (
            "protocol_error",
            "missing/duplicate finish or done, or invalid event ordering",
        )
    tokens = usage.get("completion_tokens") if isinstance(usage, dict) else None
    if type(tokens) is not int or tokens < 0:
        tokens = None
    details = usage.get("completion_tokens_details") if isinstance(usage, dict) else None
    hidden = details.get("reasoning_tokens") if isinstance(details, dict) else None
    mixed_output = any(e.kind in {"tool_metadata", "refusal"} for e in events)
    pure_text = (
        not times["tool_arguments"]
        and not times["reasoning"]
        and not mixed_output
        and hidden in (None, 0)
    )
    tpot = None
    if complete and pure_text and usage_token_scope == "text" and tokens is not None and tokens > 1:
        if times["text"]:
            tpot = (times["text"][-1] - times["text"][0]) / (tokens - 1)
    return RequestResult(
        request_id=request_id,
        status=status,
        error=error,
        sent_at_s=sent_at_s,
        ended_at_s=ended_at_s,
        first_text_delta_s=times["text"][0] if times["text"] else None,
        last_text_delta_s=times["text"][-1] if times["text"] else None,
        first_tool_arguments_delta_s=times["tool_arguments"][0]
        if times["tool_arguments"]
        else None,
        first_reasoning_delta_s=times["reasoning"][0] if times["reasoning"] else None,
        protocol_end_s=protocol_end,
        output_tokens=tokens,
        output_tokens_source="server_usage" if tokens is not None else None,
        text_tpot_proxy_s=tpot,
        output_types=[key for key, value in times.items() if value],
        text=text,
        finish_reason=finish,
        complete=complete,
        events=events,
    )


def distribution(values: list[float]) -> dict:
    """Linear interpolation at (n - 1) * q, including explicit sample count."""
    values = sorted(values)
    if not values:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "p99": None}

    def quantile(q: float) -> float:
        index = (len(values) - 1) * q
        low, high = math.floor(index), math.ceil(index)
        return values[low] + (values[high] - values[low]) * (index - low)

    return {
        "count": len(values),
        "mean": sum(values) / len(values),
        "p50": quantile(0.5),
        "p95": quantile(0.95),
        "p99": quantile(0.99),
    }


def summarize(results: list[RequestResult], execution_mode: str) -> dict:
    success = [result for result in results if result.status == "succeeded"]
    window = (
        max(r.ended_at_s for r in results) - min(r.sent_at_s for r in results) if results else 0
    )
    token_results = [r for r in success if r.output_tokens is not None]
    # Never present a subtotal of known tokens as total throughput when usage is missing.
    tokens_complete = len(token_results) == len(success) and bool(success)
    tokens = sum(r.output_tokens for r in token_results)
    return {
        "schema_version": "1.0",
        "execution_mode": execution_mode,
        "workload_origin": "synthetic",
        "sent_requests": len(results),
        "succeeded_requests": len(success),
        "failed_requests": len(results) - len(success),
        "failure_rate": (len(results) - len(success)) / len(results) if results else None,
        "status_counts": dict(Counter(r.status for r in results)),
        "measurement_window_s": window,
        "successful_requests_per_s": len(success) / window if window > 0 else None,
        "successful_output_tokens_per_s": tokens / window
        if window > 0 and tokens_complete
        else None,
        "successful_requests_with_usage": len(token_results),
        "known_successful_output_tokens": tokens,
        "failed_requests_with_partial_text": sum(bool(r.text) for r in results if not r.complete),
        "text_ttft_s": distribution(
            [r.first_text_delta_s for r in success if r.first_text_delta_s is not None]
        ),
        "text_tpot_proxy_s": distribution(
            [r.text_tpot_proxy_s for r in success if r.text_tpot_proxy_s is not None]
        ),
        "request_latency_s": distribution([r.ended_at_s - r.sent_at_s for r in success]),
        "statistical_warning": (
            "Percentiles include sample counts; small samples do not establish tail stability."
        ),
        "drain_scope": "client only; server idleness was not independently verified",
    }
