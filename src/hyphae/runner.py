"""Top‑level run orchestration.
Builds an :class:`AgentContext`, runs the Coordinator, returns the final
``RunState``. Used by the CLI and by the eval harness.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .agents.base import AgentContext
from .agents.coordinator import Coordinator, CoordinatorResult
from .artifacts import ArtifactStore
from .budget import BudgetLedger
from .ids import new_run_id
from .provenance import ProvenanceIndex
from .state import Intent, RunState
from .tools import default_registry
from .tools.registry import ToolRegistry
from .workflows.runner import LocalShellRunner, ReplayRunner, WorkflowRunner


@dataclass
class HyphaeRun:
    """Container for everything needed during a single Hyphae execution."""
    workdir: Path
    run_id: str
    artifact_store: ArtifactStore
    provenance: ProvenanceIndex
    budget: BudgetLedger
    tools: ToolRegistry
    runner: WorkflowRunner
    deterministic: bool = False
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("hyphae"))
    manifest_path: Path | None = None

    def context(self) -> AgentContext:
        """Build the AgentContext that is passed to every agent."""
        return AgentContext(
            run_id=self.run_id,
            workdir=self.workdir,
            artifact_store=self.artifact_store,
            provenance=self.provenance,
            budget=self.budget,
            tools=self.tools,
            runner=self.runner,
            deterministic=self.deterministic,
            logger=self.logger,
        )

    # Manifest handling
    def write_manifest(self) -> None:
        """
        Write a replay manifest JSON to ``self.manifest_path``.
        If the context can produce a full manifest object, we serialize that.
        Otherwise we fall back to dumping the final RunState (which is still
        sufficient for a deterministic replay).
        """
        if not self.manifest_path:
            return  # nothing to do

        try:
            # Most recent code paths expose a ``manifest()`` method on the
            # AgentContext (which builds the full provenance‑indexed manifest).
            manifest_obj = self.context().manifest()
        except Exception:  # pragma: no cover – defensive fallback
            # As a fallback, use the final RunState that was stored on the object
            # after the pipeline finished.  The CLI will set ``self.final_state``
            # before calling this method.
            if hasattr(self, "final_state"):
                manifest_obj = self.final_state
            else:
                raise RuntimeError(
                    "No manifest source available – ensure the pipeline has "
                    "completed and `self.final_state` is set before calling "
                    "`write_manifest()`."
                )

        # Write the JSON representation (pretty‑printed) to the requested file.
        self.manifest_path.write_text(manifest_obj.model_dump_json(indent=2))


def make_run(
    workdir: Path | str,
    intent: Intent,
    *,
    replay_manifest: Path | str | None = None,
    deterministic: bool = False,
    tool_registry: ToolRegistry | None = None,
    manifest_path: Path | None = None,
) -> tuple[HyphaeRun, RunState]:
    """Prepare a fresh HyphaeRun and the initial RunState."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    run_id = new_run_id(seed=str(workdir) if deterministic else None)

    artifact_store = ArtifactStore(workdir / "artifacts")
    provenance = ProvenanceIndex(workdir / "provenance.duckdb")
    budget = BudgetLedger(intent.budget)

    tools = tool_registry or default_registry()

    if replay_manifest is not None:
        runner: WorkflowRunner = ReplayRunner(replay_manifest)
    else:
        runner = LocalShellRunner()

    initial_state = RunState(run_id=run_id, intent=intent)

    return (
        HyphaeRun(
            workdir=workdir,
            run_id=run_id,
            artifact_store=artifact_store,
            provenance=provenance,
            budget=budget,
            tools=tools,
            runner=runner,
            deterministic=deterministic,
            manifest_path=manifest_path,
        ),
        initial_state,
    )


def run_default_pipeline(run: HyphaeRun, initial: RunState) -> CoordinatorResult:
    """Execute the default pipeline (Coordinator → agents)."""
    coord = Coordinator(run.context())
    return coord.run(initial)
