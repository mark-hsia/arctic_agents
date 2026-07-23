"""Opt-in end-to-end validation using real SRA data and real external tools.

Set ``RUN_REAL_SRA=1`` to enable this test.  It intentionally skips otherwise:
CI must not download public sequencing data or run a multi-hour assembly.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from hyphae.agents import CriticAgent, LiteratureAgent, ReporterAgent, StructureInferenceAgent, TargetDockingAgent
from hyphae.agents.coordinator import Coordinator
from hyphae.runner import make_run
from hyphae.state import Budget, Intent, SampleSource, TargetPathogen, apply_patch
from hyphae.tools.sra_download import SraDownloadTool
from hyphae.tools.sra_metadata_scraper import SRAMetadataScraper


ACCESSION = "SRR5832183"


def _require_real_run() -> None:
    if os.environ.get("RUN_REAL_SRA") != "1":
        pytest.skip("set RUN_REAL_SRA=1 to run the real SRA integration test")


@pytest.mark.integration
def test_golden_run_real_sra_full_pipeline(tmp_path: Path) -> None:
    """Use real metadata, reads, and local bioinformatics tools; never use stubs."""
    _require_real_run()
    try:
        metadata = SRAMetadataScraper(tmp_path / "metadata").fetch(ACCESSION)
        downloaded = SraDownloadTool().run(
            sra_accessions=[ACCESSION], output_dir=tmp_path / "fastq", use_stubs=False
        )
    except Exception as exc:
        pytest.skip(f"real SRA prerequisite unavailable: {exc}")
    assert downloaded.output_paths and all(path.is_file() for path in downloaded.output_paths)
    assert all("stub" not in str(path).lower() for path in downloaded.output_paths)

    intent = Intent(
        target_pathogen=TargetPathogen.candida_albicans,
        ecosystem="cladonia_metagenome",
        sample_sources=[SampleSource(
            kind="local_fastq", identifier=ACCESSION,
            paired=metadata["library_type"] == "PAIRED",
            metadata={"paths": [str(path) for path in downloaded.output_paths], "organism": metadata["organism"]},
        )],
        budget=Budget(max_tokens=500_000, max_dollars=25.0, max_wall_clock_seconds=7_200),
        deterministic=True,
    )
    run, initial = make_run(tmp_path / "run", intent, deterministic=True)
    result = Coordinator(run.context()).run(initial)
    state = result.final_state

    # These stages are intentionally allowed to defer when no real
    # predictor/Vina/reference evidence exists; they may not fabricate output.
    for agent in (StructureInferenceAgent(), TargetDockingAgent(), LiteratureAgent(), CriticAgent()):
        state = apply_patch(state, agent.step(state, run.context()))

    artifact_ids = {artifact.artifact_id for artifact in state.artifacts}
    assert all(Path(run.artifact_store.resolve(artifact)).is_file() for artifact in state.artifacts)
    for rationale in state.rationales:
        assert all(item in artifact_ids for item in rationale.evidence_artifact_ids)
        if "deferred" in rationale.claim.lower() or "unavailable" in rationale.claim.lower():
            assert not rationale.accepted
    for artifact in state.artifacts:
        assert not any(marker in artifact.path.lower() for marker in ("stub", "fake", "synthetic", "placeholder"))

    ReporterAgent().step(state, run.context())
    assert (run.workdir / "report" / "summary.md").is_file()
    assert (run.workdir / "report" / "run_card.json").is_file()
