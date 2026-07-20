"""Budget-aware deterministic tool planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..ids import new_rationale_id
from ..state import Rationale
from ..tools.base import ToolUnavailable
from ..tools.registry import ToolRegistry


@dataclass(frozen=True)
class ExecutionPlan:
    """One deterministic tool invocation selected by the planner."""

    step_name: str
    tool_id: str
    input_source: str
    estimated_cost_usd: float
    estimated_tokens: int


class DeterministicPlanner:
    """Produce a fixed-order plan while enforcing declared budget limits."""

    STEP_ORDER = ("ingestion", "qc", "assembly", "taxonomy", "bgc_discovery")
    DEFAULT_TOOLS = {
        "ingestion": "reads.fetch",
        "qc": "reads.qc",
        "assembly": "assembly.megahit",
        "taxonomy": "taxonomy.kraken2",
        "bgc_discovery": "bgc.antismash",
    }

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        max_tokens: int | None = None,
        max_dollars: float | None = None,
        max_wall_clock_seconds: float | None = None,
    ) -> None:
        self.registry = registry
        self.max_tokens = max_tokens
        self.max_dollars = max_dollars
        self.max_wall_clock_seconds = max_wall_clock_seconds
        self.spent_dollars = 0.0
        self.spent_tokens = 0
        self.wall_clock_budget_remaining = 0.0

    def plan(self, intent: dict[str, Any]) -> tuple[list[ExecutionPlan], list[Rationale]]:
        """Return runnable steps and the rationale for every go/no-go decision."""
        budget = intent.get("budget", {}) if isinstance(intent.get("budget", {}), dict) else {}
        max_tokens = int(self.max_tokens if self.max_tokens is not None else budget.get("max_tokens", 1_000_000))
        max_dollars = float(self.max_dollars if self.max_dollars is not None else budget.get("max_dollars", 25.0))
        max_wall = float(
            self.max_wall_clock_seconds
            if self.max_wall_clock_seconds is not None
            else budget.get("max_wall_clock_seconds", 6 * 60 * 60)
        )
        spent_dollars = 0.0
        spent_tokens = 0
        planned_wall_seconds = 0.0
        plans: list[ExecutionPlan] = []
        rationales: list[Rationale] = []

        for step_name in self.STEP_ORDER:
            config = intent.get(step_name)
            if not isinstance(config, dict):
                continue
            tool_id = str(config.get("tool_id", self.DEFAULT_TOOLS[step_name]))
            cost = float(config.get("cost_usd", 0.0))
            tokens = int(config.get("estimated_tokens", 0))
            wall_seconds = float(config.get("estimated_wall_clock_seconds", 0.0))
            input_source = str(config.get("input_source", self._default_input_source(step_name)))

            if not self._tool_exists(tool_id):
                rationales.append(self._rationale(f"Tool {tool_id} is not registered, skipping {step_name}"))
                continue
            if spent_dollars + cost > max_dollars:
                rationales.append(
                    self._rationale(f"Budget limit ${max_dollars:g} reached, skipping {step_name}")
                )
                continue
            if spent_tokens + tokens > max_tokens:
                rationales.append(
                    self._rationale(f"Token budget {max_tokens} reached, skipping {step_name}")
                )
                continue
            if planned_wall_seconds + wall_seconds > max_wall:
                rationales.append(
                    self._rationale(f"Wall-clock budget {max_wall:g}s reached, skipping {step_name}")
                )
                continue

            plans.append(ExecutionPlan(step_name, tool_id, input_source, cost, tokens))
            spent_dollars += cost
            spent_tokens += tokens
            planned_wall_seconds += wall_seconds
            rationales.append(self._rationale(f"Selected {tool_id} for {step_name}"))
        self.spent_dollars = spent_dollars
        self.spent_tokens = spent_tokens
        self.wall_clock_budget_remaining = max_wall - planned_wall_seconds
        return plans, rationales

    def _tool_exists(self, tool_id: str) -> bool:
        if hasattr(self.registry, "known_ids"):
            return tool_id in self.registry.known_ids()
        try:
            self.registry.get(tool_id)
        except (ToolUnavailable, KeyError):
            return False
        return True

    @staticmethod
    def _default_input_source(step_name: str) -> str:
        previous = {"ingestion": "", "qc": "ingestion", "assembly": "qc", "taxonomy": "assembly", "bgc_discovery": "assembly"}
        return previous[step_name]

    @staticmethod
    def _rationale(claim: str) -> Rationale:
        return Rationale(
            rationale_id=new_rationale_id("deterministic_planner", claim, deterministic=True),
            producer_agent="deterministic_planner",
            claim=claim,
        )
