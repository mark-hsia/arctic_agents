"""Planner → critic → coordinator execution loop."""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass

from ..state import RunState, RunStatePatch, apply_patch
from .assembly import AssemblyAgent
from .base import Agent, AgentContext
from .bgc_discovery import BGCDiscoveryAgent
from .critic import CriticAgent
from .ingestion import IngestionAgent
from .planner import PlannerAgent, PlanStep
from .taxonomy import TaxonomyAgent


def default_agents() -> dict[str, Agent]:
    """Discoverable built-in agent registry; callers may extend or replace it."""
    agents: Iterable[Agent] = (IngestionAgent(), AssemblyAgent(), TaxonomyAgent(), BGCDiscoveryAgent())
    return {agent.name: agent for agent in agents}


@dataclass
class CoordinatorResult:
    final_state: RunState
    agents_run: list[str]
    plan: list[PlanStep]
    failures: list[str]


class Coordinator:
    """Execute a reviewed plan while preserving partial, auditable progress."""

    def __init__(self, ctx: AgentContext, *, planner: PlannerAgent | None = None,
                 critic: CriticAgent | None = None, agents: dict[str, Agent] | None = None) -> None:
        self.ctx = ctx
        self.planner = planner or PlannerAgent()
        self.critic = critic or CriticAgent()
        self.agents = agents or default_agents()

    def run(self, initial: RunState) -> CoordinatorResult:
        proposed = self.planner.generate_plan(initial)
        review = self.critic.review_plan(proposed, set(self.agents))
        if not review.accepted:
            review = self.critic.review_plan(self.planner.static_plan(), set(self.agents))
        state = initial
        rationale = self.ctx.make_rationale(
            "coordinator", "Execution plan accepted: " + ", ".join(s.agent_name for s in review.steps)
        )
        self.ctx.record(rationales=[rationale])
        state = apply_patch(state, RunStatePatch(rationales=[rationale]))
        agents_run: list[str] = []
        failures: list[str] = []
        for step in review.steps:
            if self.ctx.budget.over_budget():
                failures.append("budget exhausted before " + step.agent_name)
                break
            started = time.monotonic()
            try:
                agent = self.agents[step.agent_name]
                self.ctx.step_params = dict(step.params or {})
                patch = agent.step(state, self.ctx)
                agent.validate_patch(patch)
                state = apply_patch(state, patch)
                self.ctx.run.executed_steps.append(
                    {
                        "tool_id": step.agent_name,
                        "kwargs": step.params or {},
                        "output_paths": getattr(patch, "output_paths", []),
                        "duration_seconds": time.monotonic() - started,
                    }
                )
                agents_run.append(step.agent_name)
            except Exception as exc:
                failures.append(f"{step.agent_name}: {exc}")
                rationale = self.ctx.make_rationale(
                    "coordinator", f"Agent {step.agent_name} failed and the run continued: {exc}"
                )
                self.ctx.record(rationales=[rationale])
                state = apply_patch(state, RunStatePatch(rationales=[rationale]))
            finally:
                self.ctx.step_params = {}
                entry = self.ctx.budget.charge(step.agent_name, wall_clock_seconds=time.monotonic() - started)
                state = apply_patch(state, RunStatePatch(budget_entries=[entry]))
        return CoordinatorResult(state, agents_run, review.steps, failures)


def build_default_graph(ctx: AgentContext) -> Coordinator:
    """Backward-compatible factory for the default dynamic coordinator."""
    return Coordinator(ctx)
