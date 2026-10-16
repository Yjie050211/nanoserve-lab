"""Raw artifacts are authoritative; summaries can be rebuilt without a backend."""

import hashlib
import json
import platform
import subprocess
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from .metrics import reduce_events, summarize
from .schemas import RequestResult, RunConfig


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def write_jsonl(path: Path, records) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            value = record.model_dump(mode="json") if hasattr(record, "model_dump") else record
            stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")


def manifest(config: RunConfig, run_id: str) -> dict:
    try:
        commit = (
            subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False, timeout=5
            ).stdout.strip()
            or None
        )
    except (OSError, subprocess.TimeoutExpired):
        commit = None
    lock = Path("uv.lock")
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "execution_mode": "fixture" if config.backend == "fixture" else "real",
        "workload_origin": "synthetic",
        "git_commit": commit,
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest() if lock.exists() else None,
        "python": platform.python_version(),
        "dependencies": {name: version(name) for name in ["httpx", "pydantic", "PyYAML"]},
        "platform": platform.platform(),
        "hardware": {"cpu": platform.processor(), "gpu": "not collected"},
        "config": config.model_dump(),
        "server_idle_verified": False,
        "notes": "Client-observed metrics only. No GPU resource or server cache claims.",
    }


def build_report(folder: Path) -> dict:
    info = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    saved = [
        RequestResult.model_validate_json(line)
        for line in (folder / "requests.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    scope = "text" if info["execution_mode"] == "fixture" else info["config"]["usage_token_scope"]
    rebuilt = [
        reduce_events(r.request_id, r.events, r.sent_at_s, r.ended_at_s, r.status, r.error, scope)
        for r in saved
    ]
    summary = summarize(rebuilt, info["execution_mode"])
    expected = info["config"]["request_count"]
    summary["unsent_requests"] = max(0, expected - len(rebuilt))
    (folder / "summary.json").write_text(json_text(summary), encoding="utf-8")
    warning = (
        "**SYNTHETIC FIXTURE: correctness evidence only, not model/GPU performance.**"
        if info["execution_mode"] == "fixture"
        else "Real HTTP client run; GPU health, cache state and server idleness are unverified."
    )
    rows = [
        f"| {key} | `{json.dumps(value, ensure_ascii=False)}` |" for key, value in summary.items()
    ]
    report = (
        f"# NanoServe run `{info['run_id']}`\n\n{warning}\n\n"
        "| Metric | Value |\n|---|---|\n" + "\n".join(rows) + "\n\n"
        "TTFT is first nonempty text delta. TPOT is a client proxy, not exact token ITL. "
        "The window includes all client completions, including failures. "
        "Raw request bodies/results may contain sensitive text; results are ignored by Git.\n"
    )
    (folder / "report.md").write_text(report, encoding="utf-8")
    return summary
