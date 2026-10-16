import json

import pytest
from pydantic import ValidationError

from nanoserve_lab.cli import execute
from nanoserve_lab.reports import build_report
from nanoserve_lab.schemas import RunConfig


@pytest.mark.parametrize(
    "value",
    [
        {"concurrency": 0},
        {"prompt_words": 0},
        {"request_count": -1},
        {"max_tokens": 0},
        {"timeout_s": 0},
        {"backend": "unknown"},
        {"backend": "http", "endpoint": "file:///secret"},
        {"unknown_key": 1},
    ],
)
def test_invalid_config(value):
    with pytest.raises(ValidationError):
        RunConfig(**value)


async def test_smoke_artifacts_and_offline_rebuild(tmp_path):
    folders = await execute(RunConfig(repetitions=2, warmup_requests=1), tmp_path)
    assert len(folders) == 2
    for folder in folders:
        info = json.loads((folder / "manifest.json").read_text())
        assert info["execution_mode"] == "fixture"
        assert info["workload_origin"] == "synthetic"
        assert info["hardware"]["gpu"] == "not collected"
        original = json.loads((folder / "summary.json").read_text())
        assert original["sent_requests"] == original["succeeded_requests"] == 6
        assert len((folder / "warmup_requests.jsonl").read_text().splitlines()) == 1
        (folder / "summary.json").unlink()
        assert build_report(folder) == original
        assert "SYNTHETIC FIXTURE" in (folder / "report.md").read_text()
