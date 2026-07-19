"""Top-level run orchestration.
Builds an :class:`AgentContext`, runs the Coordinator, returns the final
``RunState``. Used by the CLI and by the eval harness.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .agents.base import AgentContext
from .agents.coordinator import Coordinator, CoordinatorResult
from .agents.planner import PlannerAgent
from .artifacts import ArtifactStore
from .budget import BudgetLedger
from .ids import new_run_id
from .llm import LLMClient
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
    intent: Intent
    artifact_store: ArtifactStore
    provenance: ProvenanceIndex
    budget: BudgetLedger
    tools: ToolRegistry
    runner: WorkflowRunner
    deterministic: bool = False
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("hyphae"))
    manifest_path: Path | None = None
    executed_steps: list[dict] = field(default_factory=list)
    final_state: RunState | None = None

    def context(self) -> AgentContext:
        """Build the AgentContext that is passed to every agent."""
        ctx = AgentContext(
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
        ctx.run = self
        ctx.intent = self.intent
        return ctx

    def write_manifest(self, state: RunState) -> None:
        """Persist the fully resolved state used for a deterministic audit/replay."""
        if self.manifest_path:
            self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
            self.final_state = state
            self.manifest_path.write_text(
                json.dumps(
                    {
                        "run_id": self.run_id,
                        "intent": self.context().intent.model_dump(),
                        "steps": self.executed_steps,
                        "final_state": self.final_state.model_dump(),
                    },
                    indent=2,
                    default=str,
                )
            )


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
            intent=intent,
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


def run_pipeline(
    run: HyphaeRun, initial: RunState, *, llm: LLMClient | None = None
) -> CoordinatorResult:
    """Execute the reviewed dynamic plan with an optional LLM planner."""
    return Coordinator(run.context(), planner=PlannerAgent(llm)).run(initial)
