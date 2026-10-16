"""nanoserve smoke, run, and offline report commands."""

import argparse
import asyncio
import json
import os
import uuid
from pathlib import Path

import httpx
import yaml

from .backends.fixture import FixtureBackend
from .backends.http_stream import HTTPStreamBackend
from .reports import build_report, json_text, manifest, write_jsonl
from .runner import run_requests
from .schemas import RunConfig
from .workloads import build_requests


async def execute(config: RunConfig, output: Path) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240
    headers = {}
    if os.getenv("NANOSERVE_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['NANOSERVE_API_KEY']}"
    folders = []
    async with httpx.AsyncClient(
        headers=headers, timeout=config.timeout_s, trust_env=False
    ) as client:
        backend = (
            FixtureBackend(config.fixture_delay_s)
            if config.backend == "fixture"
            else HTTPStreamBackend(client, config.endpoint)
        )
        for repetition in range(config.repetitions):
            run_id = f"run-{uuid.uuid4().hex[:12]}-r{repetition + 1}"
            folder = output / run_id
            folder.mkdir()
            folders.append(folder)
            info = manifest(config, run_id)
            (folder / "manifest.json").write_text(json_text(info), encoding="utf-8")
            if config.warmup_requests:
                warm = config.model_copy(update={"request_count": config.warmup_requests})
                warm_results = await run_requests(warm, backend, build_requests(warm, "warmup"))
                write_jsonl(folder / "warmup_requests.jsonl", warm_results)
            requests = build_requests(config)
            write_jsonl(folder / "workload.jsonl", requests)
            # Flush each completed request so a later failure does not erase finished evidence.
            with (folder / "requests.jsonl").open("w", encoding="utf-8", newline="\n") as sink:

                def persist(result):
                    sink.write(result.model_dump_json() + "\n")
                    sink.flush()

                try:
                    await run_requests(config, backend, requests, persist)
                finally:
                    sink.flush()
                    build_report(folder)
    return folders


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    smoke = commands.add_parser("smoke", help="CPU synthetic fixture correctness run")
    smoke.add_argument("--output", type=Path, default=Path("results"))
    run = commands.add_parser("run", help="Run a validated YAML experiment")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output", type=Path, default=Path("results"))
    report = commands.add_parser("report", help="Recompute metrics from durable request events")
    report.add_argument("folder", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "report":
            print(json.dumps(build_report(args.folder), ensure_ascii=False, indent=2))
            return
        config = (
            RunConfig(repetitions=1)
            if args.command == "smoke"
            else RunConfig.model_validate(yaml.safe_load(args.config.read_text(encoding="utf-8")))
        )
        for folder in asyncio.run(execute(config, args.output)):
            print(folder)
    except (ValueError, OSError, yaml.YAMLError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    main()
