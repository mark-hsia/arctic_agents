"""Offline tests for structured planning, critique, and failure containment."""

from __future__ import annotations

from pathlib import Path

from hyphae.agents.base import Agent, AgentContext
from hyphae.agents.coordinator import Coordinator
from hyphae.agents.planner import PlannerAgent
from hyphae.llm import StaticLLMClient
from hyphae.runner import make_run
from hyphae.state import Intent, RunState, RunStatePatch


def test_planner_uses_valid_structured_llm_plan() -> None:
    llm = StaticLLMClient(
        [
            {"agent_name": "ingestion", "params": {"limit": 1}},
            {"agent_name": "assembly"},
            {"agent_name": "taxonomy"},
            {"agent_name": "bgc_discovery"},
        ]
    )
    plan = PlannerAgent(llm).generate_plan(RunState(run_id="run_test", intent=Intent()))
    assert [step.agent_name for step in plan] == list(PlannerAgent.DEFAULT_AGENTS)
    assert plan[0].params == {"limit": 1}


def test_planner_falls_back_for_invalid_llm_response() -> None:
    plan = PlannerAgent(StaticLLMClient([{"agent_name": "not_allowed"}])).generate_plan(
        RunState(run_id="run_test", intent=Intent())
    )
    assert [step.agent_name for step in plan] == list(PlannerAgent.DEFAULT_AGENTS)


class _FailingAgent(Agent):
    name = "ingestion"
    writes = ("samples",)

    def step(self, state: RunState, ctx: AgentContext) -> RunStatePatch:
        raise RuntimeError("expected test failure")


class _NoopAgent(Agent):
    writes = ()

    def __init__(self, name: str) -> None:
        self.name = name

    def step(self, state: RunState, ctx: AgentContext) -> RunStatePatch:
        return RunStatePatch()


class _ParameterizedAgent(_NoopAgent):
    def __init__(self, name: str, seen: list[dict]) -> None:
        super().__init__(name)
        self.seen = seen

    def step(self, state: RunState, ctx: AgentContext) -> RunStatePatch:
        self.seen.append(ctx.step_params)
        return RunStatePatch()


def test_coordinator_records_agent_failure_and_continues(tmp_path: Path) -> None:
    run, initial = make_run(tmp_path, Intent(), deterministic=True)
    agents = {
        "ingestion": _FailingAgent(),
        "assembly": _NoopAgent("assembly"),
        "taxonomy": _NoopAgent("taxonomy"),
        "bgc_discovery": _NoopAgent("bgc_discovery"),
    }
    result = Coordinator(run.context(), agents=agents).run(initial)
    assert result.agents_run == ["assembly", "taxonomy", "bgc_discovery"]
    assert result.failures == ["ingestion: expected test failure"]
    assert any("failed and the run continued" in r.claim for r in result.final_state.rationales)
    assert len(result.final_state.budget_entries) == 4


def test_coordinator_exposes_plan_parameters_to_agents(tmp_path: Path) -> None:
    run, initial = make_run(tmp_path, Intent(), deterministic=True)
    seen: list[dict] = []
    llm = StaticLLMClient(
        [
            {"agent_name": "ingestion", "params": {"source_limit": 1}},
            {"agent_name": "assembly"},
            {"agent_name": "taxonomy"},
            {"agent_name": "bgc_discovery"},
        ]
    )
    agents = {name: _ParameterizedAgent(name, seen) for name in PlannerAgent.DEFAULT_AGENTS}
    Coordinator(run.context(), planner=PlannerAgent(llm), agents=agents).run(initial)
    assert seen == [{"source_limit": 1}, {}, {}, {}]
