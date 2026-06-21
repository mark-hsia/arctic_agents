"""Coordinator (v0.1) — LangGraph state machine.

The Coordinator owns the top-level DAG. v0.1 is a deterministic rule-based
plan: ``Ingestion -> Assembly -> Taxonomy -> BGCDiscovery``. Replanning logic
and an LLM-backed planner are deferred to v0.2 (July milestone) where they
can be evaluated against the now-existing benchmark harness.

We use ``langgraph`` for the state machine even though the v0.1 graph is a
straight line, so the state-machine structure is in place when we add Critic
loops and parallel fan-out.
"""

from __future__ import annotations

from dataclasses import dataclass

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from ..state import RunState, RunStatePatch, apply_patch
from .assembly import AssemblyAgent
from .base import Agent, AgentContext
from .bgc_discovery import BGCDiscoveryAgent
from .ingestion import IngestionAgent
from .taxonomy import TaxonomyAgent


class GraphState(TypedDict):
    run_state: RunState


@dataclass
class CoordinatorResult:
    final_state: RunState
    agents_run: list[str]


def _make_node(agent: Agent, ctx: AgentContext):
    def node(graph_state: GraphState) -> GraphState:
        state = graph_state["run_state"]
        patch: RunStatePatch = agent.step(state, ctx)
        agent.validate_patch(patch)
        new_state = apply_patch(state, patch)
        return {"run_state": new_state}

    return node


def build_default_graph(ctx: AgentContext):
    """Wire the June-milestone agent path."""
    ingestion = IngestionAgent()
    assembly = AssemblyAgent()
    taxonomy = TaxonomyAgent()
    bgc = BGCDiscoveryAgent()

    sg: StateGraph = StateGraph(GraphState)
    sg.add_node("ingestion", _make_node(ingestion, ctx))
    sg.add_node("assembly", _make_node(assembly, ctx))
    sg.add_node("taxonomy", _make_node(taxonomy, ctx))
    sg.add_node("bgc_discovery", _make_node(bgc, ctx))

    sg.set_entry_point("ingestion")
    sg.add_edge("ingestion", "assembly")
    sg.add_edge("assembly", "taxonomy")
    sg.add_edge("taxonomy", "bgc_discovery")
    sg.add_edge("bgc_discovery", END)

    return sg.compile()


class Coordinator:
    """Convenience facade that compiles the graph once and runs it."""

    AGENT_ORDER = ("ingestion", "assembly", "taxonomy", "bgc_discovery")

    def __init__(self, ctx: AgentContext):
        self.ctx = ctx
        self._graph = build_default_graph(ctx)

    def run(self, initial: RunState) -> CoordinatorResult:
        final = self._graph.invoke({"run_state": initial})
        return CoordinatorResult(
            final_state=final["run_state"],
            agents_run=list(self.AGENT_ORDER),
        )
