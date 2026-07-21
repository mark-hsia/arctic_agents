"""Graceful, artifact-producing executor for deterministic tool plans."""

from __future__ import annotations
import logging
import time
from pathlib import Path
from typing import Any

from hyphae.manifest import Manifest, StepResult, Artifact, Rationale, BudgetEntry
from hyphae.tools.registry import ToolRegistry
from hyphae.runtime.deterministic_planner import ExecutionPlan

logger = logging.getLogger(__name__)


class DeterministicExecutor:
    """Execute plans in order, recording failures instead of aborting the run."""

    def __init__(self) -> None:
        self.budget_tracker: dict[str, float | int] = {
            "tokens_used": 0,
            "dollars_used": 0.0,
            "wall_clock_seconds": 0.0,
        }
        self.start_time = time.time()

    def execute(
        self,
        plans: list[ExecutionPlan],
        registry: ToolRegistry,
        workdir: Path,
        manifest_in: Manifest | None = None,
    ) -> Manifest:
        """Execute all plans in order. Never crashes; logs failures as rationales."""
        manifest = manifest_in or Manifest(run_id="exec_run")
        workdir.mkdir(parents=True, exist_ok=True)

        for plan in plans:
            step_start = time.time()
            step_result = StepResult(
                step_name=plan.step_name,
                tool_id=plan.tool_id,
                duration_seconds=0.0,
            )

            try:
                tool = self._get_tool(registry, plan.tool_id)

                parent_artifacts = []
                if plan.input_source:
                    for artifact in manifest.artifacts:
                        if artifact.producer_agent == plan.input_source:
                            parent_artifacts.append(artifact)

                result = tool.run(
                    input_paths=[str(a.path) for a in parent_artifacts],
                    output_dir=str(workdir / plan.step_name),
                )

                for output_path in result.output_paths:
                    artifact = Artifact(
                        artifact_id=f"art_{plan.step_name}_{len(manifest.artifacts)}",
                        path=str(output_path),
                        producer_agent=plan.step_name,
                        mime_type="application/octet-stream",
                    )
                    manifest.add_artifact(artifact)
                    step_result.output_paths.append(output_path)

                # POPULATE final_state BASED ON STEP NAME
                if plan.step_name == "assembly":
                    manifest.final_state.setdefault("assemblies", {})[f"sample_{len(manifest.final_state.get('assemblies', {}))}"] = str(output_path)

                elif plan.step_name == "qc":
                    manifest.final_state.setdefault("qc_reports", []).append(str(output_path))

                step_result.success = True
                rationale_claim = f"Executed {plan.tool_id} successfully, produced {len(result.output_paths)} outputs"

            except Exception as e:
                step_result.success = False
                step_result.error = str(e)
                rationale_claim = f"Tool {plan.tool_id} failed: {e}. Continuing."
                logger.warning(f"Tool {plan.tool_id} failed: {e}")

            step_result.duration_seconds = time.time() - step_start
            manifest.add_step(step_result)

            rationale = Rationale(
                rationale_id=f"rat_{manifest.run_id}_{len(manifest.rationales)}",
                producer_agent="executor",
                claim=rationale_claim,
                evidence_artifact_ids=[a.artifact_id for a in manifest.artifacts if a.producer_agent == plan.step_name],
                accepted=True,
                critic_comments=[],
            )
            manifest.add_rationale(rationale)

            budget_entry = BudgetEntry(
                agent=plan.step_name,
                tokens=0,
                dollars=plan.estimated_cost_usd,
                wall_clock_seconds=step_result.duration_seconds,
            )
            manifest.add_budget_entry(budget_entry)

        return manifest

    def _get_tool(self, registry: ToolRegistry, tool_id: str):
        """Get tool from registry."""
        return registry.get(tool_id)
