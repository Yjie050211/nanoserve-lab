"""Validated experiment configuration and durable, nullable result records."""

from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

SUPPORTED_FINISH_REASONS = frozenset(
    {"stop", "length", "tool_calls", "content_filter", "function_call"}
)


def valid_finish_reason(value: Any) -> bool:
    """Only recognized protocol terminal reasons prove a supported stream completed."""
    return isinstance(value, str) and value in SUPPORTED_FINISH_REASONS


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    backend: Literal["fixture", "http"] = "fixture"
    endpoint: str = "http://127.0.0.1:8000/v1/chat/completions"
    model: str = "fixture-model"
    request_count: int = Field(default=6, ge=1, le=100000)
    concurrency: int = Field(default=2, ge=1, le=1024)
    prompt_words: int = Field(default=32, ge=1, le=100000)
    max_tokens: int = Field(default=16, ge=1)
    timeout_s: float = Field(default=30, gt=0, le=3600)
    warmup_requests: int = Field(default=0, ge=0)
    repetitions: int = Field(default=3, ge=1, le=100)
    seed: int = 42
    # Explicit assertion about the selected model/server; never infer from SSE chunk count.
    usage_token_scope: Literal["unknown", "text"] = "unknown"
    cache_state: str = "unknown"
    model_revision: str | None = None
    tokenizer_revision: str | None = None
    chat_template_sha256: str | None = None
    engine_version: str | None = None
    image_digest: str | None = None
    fixture_delay_s: float = Field(default=0.001, ge=0, le=10)

    @model_validator(mode="after")
    def validate_endpoint(self):
        if self.backend == "http" and not self.endpoint.startswith(("http://", "https://")):
            raise ValueError("HTTP endpoint must use http:// or https://")
        endpoint = urlsplit(self.endpoint)
        if endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
            raise ValueError(
                "credentials/query/fragment forbidden in endpoint; use NANOSERVE_API_KEY"
            )
        if not endpoint.hostname:
            raise ValueError("endpoint must contain a host")
        return self


class RequestSpec(BaseModel):
    request_id: str
    body: dict[str, Any]


class StreamEvent(BaseModel):
    kind: Literal[
        "role",
        "text",
        "tool_arguments",
        "tool_metadata",
        "reasoning",
        "refusal",
        "usage",
        "finish",
        "done",
        "error",
    ]
    elapsed_s: float = Field(ge=0)
    data: Any = None


class RequestResult(BaseModel):
    request_id: str
    status: Literal["succeeded", "http_error", "protocol_error", "timeout", "cancelled", "error"]
    sent_at_s: float
    ended_at_s: float
    attempts: int = 1
    error: str | None = None
    first_text_delta_s: float | None = None
    last_text_delta_s: float | None = None
    first_tool_arguments_delta_s: float | None = None
    first_reasoning_delta_s: float | None = None
    protocol_end_s: float | None = None
    output_tokens: int | None = None
    output_tokens_source: str | None = None
    text_tpot_proxy_s: float | None = None
    output_types: list[str] = Field(default_factory=list)
    text: str = ""
    finish_reason: str | None = None
    complete: bool = False
    events: list[StreamEvent] = Field(default_factory=list)
