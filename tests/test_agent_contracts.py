"""Contract-level checks for the typed Hyphae agents."""

from __future__ import annotations


def test_agent_reads_writes_contracts() -> None:
    from hyphae.agents import (
        AssemblyAgent, BGCDiscoveryAgent, CriticAgent, IngestionAgent,
        LiteratureAgent, StructureInferenceAgent, TargetDockingAgent, TaxonomyAgent,
    )

    agents = [
        IngestionAgent(), AssemblyAgent(), TaxonomyAgent(), BGCDiscoveryAgent(),
        StructureInferenceAgent(), TargetDockingAgent(), LiteratureAgent(), CriticAgent(),
    ]
    free = {"rationales", "artifacts", "budget_entries"}
    writes: dict[str, str] = {}
    for agent in agents:
        assert isinstance(agent.reads, tuple)
        assert isinstance(agent.writes, tuple)
        assert agent.name
        for key in agent.writes:
            if key not in free:
                assert key not in writes, f"{key} written by {writes[key]} and {agent.name}"
                writes[key] = agent.name


def test_no_agent_produces_synthetic_data() -> None:
    import pytest

    from hyphae.agents import (
        AssemblyAgent, BGCDiscoveryAgent, CriticAgent, IngestionAgent,
        LiteratureAgent, StructureInferenceAgent, TargetDockingAgent, TaxonomyAgent,
    )
    from hyphae.no_synthetic_data import _check_patch_for_synthetic
    from hyphae.state import RunStatePatch

    agents = [
        IngestionAgent(), AssemblyAgent(), TaxonomyAgent(), BGCDiscoveryAgent(),
        StructureInferenceAgent(), TargetDockingAgent(), LiteratureAgent(), CriticAgent(),
    ]
    for agent in agents:
        assert hasattr(agent.step, "__wrapped__")
        _check_patch_for_synthetic(RunStatePatch(rationales=[{
            "rationale_id": "rat_deferred", "producer_agent": agent.name,
            "claim": "Tool unavailable; deferred.", "accepted": False,
        }]), agent.name)
    with pytest.raises(ValueError, match="placeholder"):
        _check_patch_for_synthetic(RunStatePatch(structures={"bgc_1": [{
            "structure_id": "structure_1", "bgc_id": "bgc_1", "smiles": "C",
            "confidence": 0.1, "method": "test",
        }]}), "structure")
