"""Planner that proposes an ordered, allow-listed agent execution plan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from ..llm import LLMClient
from ..state import RunState


@dataclass(frozen=True)
class PlanStep:
    agent_name: str
    params: dict[str, Any] | None = None


class PlannerAgent:
    """Generate a structured plan, falling back safely when the LLM fails."""

    DEFAULT_AGENTS = ("ingestion", "assembly", "taxonomy", "bgc_discovery")
    PLAN_SCHEMA: ClassVar[dict[str, Any]] = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string"},
                "params": {"type": "object"},
            },
            "required": ["agent_name"],
            "additionalProperties": False,
        },
    }

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm

    def static_plan(self) -> list[PlanStep]:
        return [PlanStep(name) for name in self.DEFAULT_AGENTS]

    def generate_plan(self, state: RunState) -> list[PlanStep]:
        if self.llm is None:
            return self.static_plan()
        try:
            raw = self.llm.complete(
                prompt=(
                    "Plan this Hyphae metagenomics run. Return only a JSON array "
                    "of {agent_name, params?} objects. Agent names may only be: "
                    f"{', '.join(self.DEFAULT_AGENTS)}.\nIntent:\n"
                    f"{state.intent.model_dump_json()}"
                ),
                response_schema=self.PLAN_SCHEMA,
            )
            return self._parse_plan(raw)
        except Exception:
            return self.static_plan()

    @classmethod
    def _parse_plan(cls, raw: Any) -> list[PlanStep]:
        if not isinstance(raw, list) or not raw:
            raise ValueError("plan must be a non-empty JSON array")
        plan: list[PlanStep] = []
        for item in raw:
            if not isinstance(item, dict) or set(item) - {"agent_name", "params"}:
                raise ValueError("invalid plan step")
            name = item.get("agent_name")
            params = item.get("params")
            if name not in cls.DEFAULT_AGENTS or (params is not None and not isinstance(params, dict)):
                raise ValueError("unknown agent or invalid parameters")
            plan.append(PlanStep(name, params))
        return plan
