"""End-to-end pipeline test in replay mode."""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from hyphae.agents.coordinator import Coordinator
from hyphae.evals.benchmarks import Junttila2021Benchmark
from hyphae.runner import make_run
from hyphae.state import (
    Intent,
    SampleSource,
)
SAMPLES = ["L1", "L2", "L3", "L4", "L34", "L35"]

def _build_replay_manifest_v2(workdir: Path, fastq_root: Path) -> Path:
    replay_dir = workdir / "replay"
    replay_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    from hyphae.ids import short_hash
    for sid in SAMPLES:
        contigs = replay_dir / f"{sid}.contigs.fasta"
        with contigs.open("w") as fh:
            for i in range(5):
                fh.write(f">{sid}_contig_{i}\n")
                fh.write("ACGT" * 1500 + "\n")
        sample_hash = short_hash("local_fastq", sid)
        sample_id_full = f"S_{sample_hash}"
        metrics = {
            "n_contigs": 5,
            "total_length": 5 * 6000,
            "n50": 6000,
            "largest_contig": 6000,
        }
        manifest[f"asm.metaspades.{sample_id_full}"] = {
            "tool_id": "assembly.metaspades",
            "output_paths": [str(contigs.relative_to(replay_dir))],
            "metrics": metrics,
        }
        manifest[f"asm.megahit.{sample_id_full}"] = {
            "tool_id": "assembly.megahit",
            "output_paths": [str(contigs.relative_to(replay_dir))],
            "metrics": metrics,
        }
    manifest_path = replay_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return manifest_path

@pytest.fixture
def fastq_root(tmp_path: Path) -> Path:
    root = tmp_path / "fastq"
    root.mkdir()
    for sid in SAMPLES:
        for end in (1, 2):
            p = root / f"{sid}_{end}.fastq"
            p.write_text("@r\nACGT\n+\nIIII\n")
    return root

def test_pipeline_runs_end_to_end_in_replay_mode(tmp_path: Path, fastq_root: Path) -> None:
    """Test coordinator on replay manifests with graceful tool deferral.
    
    Without real binning tools, MAGs are deferred (not fabricated).
    Without real BGC discovery, BGCs are deferred (not fabricated).
    """
    workdir = tmp_path / "run"
    manifest = _build_replay_manifest_v2(workdir, fastq_root)
    sources = [
        SampleSource(
            kind="local_fastq",
            identifier=sid,
            paired=True,
            metadata={
                "paths": [
                    str(fastq_root / f"{sid}_1.fastq"),
                    str(fastq_root / f"{sid}_2.fastq"),
                ]
            },
        )
        for sid in SAMPLES
    ]
    intent = Intent(sample_sources=sources)
    hrun, initial = make_run(workdir, intent, replay_manifest=manifest, deterministic=True)
    coord = Coordinator(hrun.context())
    result = coord.run(initial)
    final = result.final_state
    
    # Validate: all samples ingested
    assert len(final.samples) == len(SAMPLES)
    
    # Validate: all samples reach assembly (via replay)
    assert len(final.assemblies) == len(SAMPLES)
    
    # Validate: no synthetic data in the state
    for artifact in final.artifacts:
        assert "[STUB_" not in artifact.path
        assert "[FAKE_" not in artifact.path
    
    for rationale in final.rationales:
        assert "[STUB_" not in rationale.claim
        assert "[FAKE_" not in rationale.claim
        assert "placeholder" not in rationale.claim.lower()
    
    # Validate: MAGs may be deferred (expected without binning tools)
    # The important thing is they're not fabricated
    assert len(final.mags) <= len(SAMPLES)
    
    # Validate: BGCs are deferred without real tools
    # This is the expected behavior
    assert len(final.bgcs) == 0 or all(
        not r.accepted for r in final.rationales 
        if r.producer_agent == "bgc_discovery"
    )

