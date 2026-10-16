import json
from pathlib import Path

import pytest

from nanoserve_lab.metrics import reduce_events, summarize
from nanoserve_lab.schemas import StreamEvent

GOLDEN = json.loads((Path(__file__).parent / "fixtures/stream-metrics-v1.json").read_text())


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda item: item["name"])
def test_shared_golden_metrics(case):
    events = []
    sent = case["sent_at_ms"] / 1000
    for item in case["events"]:
        at = item["at_ms"] / 1000 - sent
        kind = item["kind"]
        if kind == "metadata":
            continue
        data = item.get("text")
        if kind == "usage":
            data = {
                "completion_tokens": item["completion_tokens"],
                "completion_tokens_details": {"reasoning_tokens": item["reasoning_tokens"]},
            }
        if kind == "done":
            # The cross-project fixture describes semantic completion; inject the HTTP
            # adapter's stricter finish marker at that same instant.
            events.append(StreamEvent(kind="finish", elapsed_s=at, data="stop"))
        events.append(StreamEvent(kind=kind, elapsed_s=at, data=data))
    end = case["events"][-1]["at_ms"] / 1000
    result = reduce_events(case["name"], events, sent, end, "succeeded", None, "text")
    assert result.status == "succeeded"
    for actual, expected in [
        (result.first_text_delta_s, case["expected"]["text_ttft_ms"]),
        (result.text_tpot_proxy_s, case["expected"]["text_tpot_proxy_ms"]),
    ]:
        assert actual is None if expected is None else actual == pytest.approx(expected / 1000)
    assert result.ended_at_s - result.sent_at_s == pytest.approx(case["expected"]["e2e_ms"] / 1000)


def make_result(status="succeeded", tokens=3, scope="text", extra=None, end=0.5):
    events = [
        StreamEvent(kind="text", elapsed_s=0.1, data="a"),
        StreamEvent(kind="text", elapsed_s=0.3, data="b"),
    ]
    if extra:
        events.append(StreamEvent(kind=extra, elapsed_s=0.31, data="other"))
    events += [
        StreamEvent(kind="usage", elapsed_s=0.35, data={"completion_tokens": tokens}),
        StreamEvent(kind="finish", elapsed_s=0.4, data="stop"),
        StreamEvent(kind="done", elapsed_s=0.45),
    ]
    return reduce_events("r", events, 0, end, status, None, scope)


@pytest.mark.parametrize("tokens", [None, 0, 1, -1, True, "3"])
def test_unreliable_or_small_usage_has_no_tpot(tokens):
    assert make_result(tokens=tokens).text_tpot_proxy_s is None


@pytest.mark.parametrize("extra", ["reasoning", "tool_arguments", "tool_metadata", "refusal"])
def test_mixed_output_has_no_text_tpot(extra):
    assert make_result(extra=extra).text_tpot_proxy_s is None


def test_unknown_scope_and_incomplete_never_get_tpot():
    assert make_result(scope="unknown").text_tpot_proxy_s is None
    assert make_result(status="timeout").text_tpot_proxy_s is None
    incomplete = reduce_events(
        "r", [StreamEvent(kind="text", elapsed_s=0.1, data="x")], 0, 0.5, "succeeded", None, "text"
    )
    assert incomplete.status == "protocol_error"


@pytest.mark.parametrize("reason", ["", " ", "future_unsupported", 123])
def test_offline_reduction_rejects_invalid_finish_reason(reason):
    original = make_result()
    events = [
        event.model_copy(update={"data": reason}) if event.kind == "finish" else event
        for event in original.events
    ]
    rebuilt = reduce_events("r", events, 0, 0.5, "succeeded", None, "text")
    assert rebuilt.status == "protocol_error"
    assert not rebuilt.complete
    assert rebuilt.text_tpot_proxy_s is None


def test_throughput_includes_failed_tail_and_missing_usage_is_null():
    good = make_result()
    failure = make_result(status="timeout", end=2)
    summary = summarize([good, failure], "real")
    assert summary["failure_rate"] == 0.5
    assert summary["measurement_window_s"] == 2
    assert summary["successful_requests_per_s"] == 0.5
    assert summary["successful_output_tokens_per_s"] == 1.5
    assert (
        summarize([good, make_result(tokens=None)], "real")["successful_output_tokens_per_s"]
        is None
    )
