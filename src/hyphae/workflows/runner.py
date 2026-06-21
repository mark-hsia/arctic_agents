"""Workflow runners.

Heavy bio steps are submitted as :class:`StepSpec` objects to a runner. This
keeps agents pure (they decide what to run) and lets us swap execution
between local shell, dry-run, replay, and Snakemake without touching agents.

The June milestone exit criterion ("re-run is bit-identical") leans on the
:class:`ReplayRunner` plus the content-addressed artifact store.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..tools.base import Tool, ToolRunResult, ToolUnavailable
from ..tools.registry import ToolRegistry


@dataclass
class StepSpec:
    """A single tool invocation request."""

    step_id: str
    tool_id: str
    kwargs: dict[str, Any] = field(default_factory=dict)
    description: str | None = None


class WorkflowRunner(ABC):
    """Executes :class:`StepSpec` requests.

    ``run(tool, step)`` is the low-level call. ``execute(step, registry)`` is
    the agent-facing call that lets a runner decide whether to consult the
    registry at all (replay mode skips the lookup so missing binaries don't
    block a recorded run).
    """

    @abstractmethod
    def run(self, tool: Tool | None, step: StepSpec) -> ToolRunResult: ...

    def execute(self, step: StepSpec, registry: ToolRegistry) -> ToolRunResult:
        try:
            tool: Tool | None = registry.get(step.tool_id)
        except ToolUnavailable:
            tool = None
        return self.run(tool, step)


class LocalShellRunner(WorkflowRunner):
    """Calls ``tool.run(**step.kwargs)``. Raises if no tool is available."""

    def run(self, tool: Tool | None, step: StepSpec) -> ToolRunResult:
        if tool is None:
            raise ToolUnavailable(
                f"LocalShellRunner cannot execute step '{step.step_id}': "
                f"no available implementation for tool '{step.tool_id}'"
            )
        return tool.run(**step.kwargs)


class DryRunRunner(WorkflowRunner):
    """Records intended invocations without executing them. Useful for
    plan inspection and CI sanity."""

    def __init__(self) -> None:
        self.calls: list[StepSpec] = []

    def run(self, tool: Tool | None, step: StepSpec) -> ToolRunResult:
        self.calls.append(step)
        return ToolRunResult(
            tool_id=step.tool_id,
            output_paths=[],
            metrics={"dry_run": True},
            stdout="",
            stderr="",
            return_code=0,
        )


class ReplayRunner(WorkflowRunner):
    """Returns pre-recorded outputs for known step IDs.

    Drives the eval harness end-to-end without any bio tools installed.
    The replay manifest is JSON of the form::

        {
            "step_id": {
                "tool_id": "bgc.antismash",
                "output_paths": ["replay/.../foo.json"],
                "metrics": {"n_clusters": 12}
            }
        }

    Paths are resolved relative to ``manifest_dir`` (defaults to the manifest
    file's parent).
    """

    def __init__(self, manifest_path: Path | str):
        self.manifest_path = Path(manifest_path)
        self.manifest_dir = self.manifest_path.parent
        self._manifest: dict[str, dict[str, Any]] = json.loads(
            self.manifest_path.read_text()
        )

    def has(self, step_id: str) -> bool:
        return step_id in self._manifest

    def run(self, tool: Tool | None, step: StepSpec) -> ToolRunResult:
        if step.step_id not in self._manifest:
            raise ToolUnavailable(
                f"No replay entry for step '{step.step_id}' "
                f"(tool_id={step.tool_id})"
            )
        rec = self._manifest[step.step_id]
        if rec["tool_id"] != step.tool_id:
            raise ValueError(
                f"Replay tool_id mismatch for {step.step_id}: "
                f"recorded={rec['tool_id']!r} requested={step.tool_id!r}"
            )
        outs = [self.manifest_dir / p for p in rec.get("output_paths", [])]
        return ToolRunResult(
            tool_id=step.tool_id,
            output_paths=outs,
            metrics=dict(rec.get("metrics", {})),
            stdout=rec.get("stdout", ""),
            stderr=rec.get("stderr", ""),
            return_code=int(rec.get("return_code", 0)),
            duration_seconds=float(rec.get("duration_seconds", 0.0)),
            tool_version=rec.get("tool_version"),
        )


class SnakemakeRunner(WorkflowRunner):  # pragma: no cover - shells out
    """Submits a step as a Snakemake job and waits.

    Stub for v0.1: emits a single-rule Snakefile with the tool invocation. A
    real implementation will template DAGs and use Snakemake's caching so
    re-runs hit identical artifact hashes.
    """

    def run(self, tool: Tool | None, step: StepSpec) -> ToolRunResult:
        raise NotImplementedError(
            "SnakemakeRunner is a v0.2 deliverable; use LocalShellRunner or ReplayRunner"
        )
