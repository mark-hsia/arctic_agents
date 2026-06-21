"""ReplayRunner exercise.

The replay runner is what lets the eval harness drive the full pipeline
without bio tools installed. This test builds a tiny manifest and confirms
each step's outputs come back as recorded.
"""

from __future__ import annotations

import json
from pathlib import Path

from hyphae.tools.base import Tool, ToolRunResult
from hyphae.workflows.runner import ReplayRunner, StepSpec


class _DummyTool(Tool):
    tool_id = "x.dummy"
    binary = None

    def run(self, **kwargs):  # type: ignore[no-untyped-def]
        return ToolRunResult(tool_id=self.tool_id)


def test_replay_runner_returns_recorded_outputs(tmp_path: Path) -> None:
    out_path = tmp_path / "fake.txt"
    out_path.write_text("recorded")
    manifest = {
        "step1": {
            "tool_id": "x.dummy",
            "output_paths": [str(out_path.relative_to(tmp_path))],
            "metrics": {"n": 7},
        }
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    runner = ReplayRunner(manifest_path)
    res = runner.run(_DummyTool(), StepSpec(step_id="step1", tool_id="x.dummy"))
    assert res.metrics["n"] == 7
    assert res.output_paths[0].read_text() == "recorded"
