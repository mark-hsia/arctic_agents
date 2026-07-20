"""Graceful, artifact-producing executor for deterministic tool plans."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..artifacts import ArtifactStore
from ..ids import new_rationale_id
from ..state import Artifact, BudgetEntry, Rationale
from ..tools.base import ToolRunResult
from ..tools.registry import ToolRegistry
from .deterministic_planner import ExecutionPlan

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    step_name: str
    tool_id: str
    duration_seconds: float
    output_artifact_ids: list[str] = field(default_factory=list)
    success: bool = True
    error: str | None = None


@dataclass
class Manifest:
    """Portable execution record used by the deterministic runtime."""

    run_id: str = "deterministic"
    steps: list[StepResult] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    rationales: list[Rationale] = field(default_factory=list)
    budget_entries: list[BudgetEntry] = field(default_factory=list)
    final_state: dict[str, Any] = field(
        default_factory=lambda: {"samples": [], "assemblies": {}, "taxonomy": [], "bgcs": []}
    )


class DeterministicExecutor:
    """Execute plans in order, recording failures instead of aborting the run."""

    def __init__(self) -> None:
        self.budget_tracker: dict[str, float | int] = {
            "tokens_used": 0,
            "dollars_used": 0.0,
            "wall_start_time": 0.0,
        }

    def execute(
        self,
        plans: list[ExecutionPlan],
        registry: ToolRegistry,
        workdir: Path,
        manifest_in: Manifest | None = None,
    ) -> Manifest:
        manifest = manifest_in or Manifest()
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        store = ArtifactStore(workdir / "artifacts")
        budget_tracker = {"tokens_used": 0, "dollars_used": 0.0, "wall_start_time": time.monotonic()}
        self.budget_tracker = budget_tracker

        for plan in plans:
            started = time.monotonic()
            parent_artifacts = self._resolve_inputs(manifest, store, plan.input_source)
            try:
                tool = self._get_tool(registry, plan.tool_id)
                result = tool.run(
                    input_paths=[str(store.resolve(artifact)) for artifact in parent_artifacts],
                    output_dir=str(workdir / plan.step_name),
                )
                if not isinstance(result, ToolRunResult):
                    raise TypeError(f"{plan.tool_id} returned {type(result).__name__}, not ToolRunResult")
                artifacts = self._record_outputs(manifest, store, result, plan, parent_artifacts)
                duration = time.monotonic() - started
                manifest.steps.append(
                    StepResult(plan.step_name, plan.tool_id, duration, [a.artifact_id for a in artifacts])
                )
                manifest.rationales.append(self._rationale(
                    f"Ran {plan.tool_id}, produced {len(artifacts)} outputs",
                    [a.artifact_id for a in artifacts],
                ))
                self._update_final_state(manifest, plan.step_name, artifacts)
            except Exception as exc:  # The executor is deliberately failure-tolerant.
                duration = time.monotonic() - started
                logger.exception("Tool %s failed", plan.tool_id)
                manifest.steps.append(StepResult(plan.step_name, plan.tool_id, duration, success=False, error=str(exc)))
                manifest.rationales.append(self._rationale(f"Tool {plan.tool_id} failed: {exc}"))
            finally:
                budget_tracker["tokens_used"] += plan.estimated_tokens
                budget_tracker["dollars_used"] += plan.estimated_cost_usd
                manifest.budget_entries.append(BudgetEntry(
                    agent=plan.step_name,
                    tokens=plan.estimated_tokens,
                    dollars=plan.estimated_cost_usd,
                    wall_clock_seconds=time.monotonic() - started,
                ))
        return manifest

    @staticmethod
    def _get_tool(registry: ToolRegistry, tool_id: str):
        getter = getattr(registry, "get_tool", None) or registry.get
        return getter(tool_id)

    @staticmethod
    def _resolve_inputs(manifest: Manifest, store: ArtifactStore, source: str) -> list[Artifact]:
        if not source:
            return []
        by_id = {artifact.artifact_id: artifact for artifact in manifest.artifacts}
        if source in by_id:
            return [by_id[source]]
        for step in reversed(manifest.steps):
            if step.step_name == source:
                return [by_id[artifact_id] for artifact_id in step.output_artifact_ids if artifact_id in by_id]
        return []

    @staticmethod
    def _record_outputs(
        manifest: Manifest,
        store: ArtifactStore,
        result: ToolRunResult,
        plan: ExecutionPlan,
        parents: list[Artifact],
    ) -> list[Artifact]:
        artifacts: list[Artifact] = []
        for output in result.output_paths:
            path = Path(output)
            if not path.is_file():
                logger.warning("Tool %s reported missing output %s", plan.tool_id, path)
                continue
            artifact = store.put_path(
                path,
                producer_agent=plan.step_name,
                run_id=manifest.run_id,
                parent_ids=[parent.artifact_id for parent in parents],
                tool_version=result.tool_version,
                metadata={"tool_id": plan.tool_id, "metrics": result.metrics},
            )
            manifest.artifacts.append(artifact)
            artifacts.append(artifact)
        return artifacts

    @staticmethod
    def _update_final_state(manifest: Manifest, step_name: str, artifacts: list[Artifact]) -> None:
        paths = [artifact.path for artifact in artifacts]
        if step_name == "ingestion":
            manifest.final_state["samples"] = paths
        elif step_name == "assembly":
            manifest.final_state["assemblies"] = {artifact.artifact_id: artifact.path for artifact in artifacts}
        elif step_name == "taxonomy":
            manifest.final_state["taxonomy"] = paths
        elif step_name == "bgc_discovery":
            manifest.final_state["bgcs"] = paths

    @staticmethod
    def _rationale(claim: str, artifact_ids: list[str] | None = None) -> Rationale:
        return Rationale(
            rationale_id=new_rationale_id("deterministic_executor", claim, deterministic=True),
            producer_agent="deterministic_executor",
            claim=claim,
            evidence_artifact_ids=artifact_ids or [],
            accepted=True,
        )
