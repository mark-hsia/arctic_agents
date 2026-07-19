"""Deterministic guardrail for planner output and specialist failures."""

from __future__ import annotations

from dataclasses import dataclass

from .planner import PlanStep


@dataclass(frozen=True)
class PlanReview:
    accepted: bool
    steps: list[PlanStep]
    comments: list[str]


class CriticAgent:
    """Reject plans that are unsafe, incomplete, or not dependency ordered."""

    REQUIRED_ORDER = ("ingestion", "assembly", "taxonomy", "bgc_discovery")

    def review_plan(self, plan: list[PlanStep], available_agents: set[str]) -> PlanReview:
        names = [step.agent_name for step in plan]
        if len(names) != len(set(names)):
            return PlanReview(False, [], ["plan contains duplicate agents"])
        if any(name not in available_agents for name in names):
            return PlanReview(False, [], ["plan contains an unavailable agent"])
        positions = [names.index(name) if name in names else -1 for name in self.REQUIRED_ORDER]
        if any(position < 0 for position in positions):
            return PlanReview(False, [], ["plan omits a required pipeline stage"])
        if positions != sorted(positions):
            return PlanReview(False, [], ["plan violates required data dependencies"])
        return PlanReview(True, plan, [])
