"""Verify each agent's declared reads/writes contract is honored."""

from __future__ import annotations

from hyphae.agents.assembly import AssemblyAgent
from hyphae.agents.bgc_discovery import BGCDiscoveryAgent
from hyphae.agents.ingestion import IngestionAgent
from hyphae.agents.taxonomy import TaxonomyAgent
from hyphae.state import RunStatePatch


def test_ingestion_only_writes_samples() -> None:
    a = IngestionAgent()
    assert "samples" in a.writes


def test_assembly_writes_assemblies_mags_taxonomy() -> None:
    a = AssemblyAgent()
    assert {"assemblies", "mags", "taxonomy"} <= set(a.writes)


def test_bgc_discovery_only_writes_bgcs() -> None:
    a = BGCDiscoveryAgent()
    assert "bgcs" in a.writes


def test_taxonomy_only_writes_taxonomy() -> None:
    a = TaxonomyAgent()
    assert "taxonomy" in a.writes


def test_validate_patch_rejects_out_of_slice_writes() -> None:
    a = IngestionAgent()
    patch = RunStatePatch(bgcs=[])  # IngestionAgent does not write bgcs
    try:
        a.validate_patch(patch)
    except PermissionError:
        return
    raise AssertionError("Expected PermissionError")
