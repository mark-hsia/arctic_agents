"""Top-level run orchestration.

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
    workdir: Path
    run_id: str
    artifact_store: ArtifactStore
    provenance: ProvenanceIndex
    budget: BudgetLedger
    tools: ToolRegistry
    runner: WorkflowRunner
    deterministic: bool = False
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("hyphae"))

    def context(self) -> AgentContext:
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


def make_run(
    workdir: Path | str,
    intent: Intent,
    *,
    replay_manifest: Path | str | None = None,
    deterministic: bool = False,
    tool_registry: ToolRegistry | None = None,
) -> tuple[HyphaeRun, RunState]:
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
        ),
        initial_state,
    )


def run_default_pipeline(run: HyphaeRun, initial: RunState) -> CoordinatorResult:
    coord = Coordinator(run.context())
    return coord.run(initial)
