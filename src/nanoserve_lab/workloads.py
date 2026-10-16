"""Deterministic synthetic prompts; word count is not a tokenizer token count."""

import random

from .schemas import RequestSpec, RunConfig


def build_requests(config: RunConfig, prefix: str = "request") -> list[RequestSpec]:
    rng = random.Random(config.seed)
    vocabulary = ["system", "request", "queue", "memory", "compute", "token", "trace"]
    requests = []
    for i in range(config.request_count):
        words = " ".join(rng.choice(vocabulary) for _ in range(config.prompt_words))
        requests.append(
            RequestSpec(
                request_id=f"{prefix}-{i:05d}",
                body={
                    "model": config.model,
                    "messages": [{"role": "user", "content": f"Summarize this sequence: {words}"}],
                    "temperature": 0,
                    "max_tokens": config.max_tokens,
                    "n": 1,
                    "stream": True,
                    "stream_options": {"include_usage": True},
                },
            )
        )
    return requests
