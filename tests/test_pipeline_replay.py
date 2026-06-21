"""End-to-end pipeline test in replay mode.

Drives the Coordinator graph (Ingestion -> Assembly -> Taxonomy ->
BGCDiscovery) using a synthetic dataset shaped like Junttila et al. 2021,
without any bio tools installed. Confirms:

  * The agent contracts hold (no PermissionError).
  * The replay runner serves recorded artifacts.
  * The Junttila benchmark scoring produces a sensible result given a
    deliberately weak run (zero BGCs because we replay only assembly).
  * Provenance index records artifacts and rationales as the run progresses.
"""

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


def _build_replay_manifest(workdir: Path) -> Path:
    """Synthesize per-sample replay outputs that look like real metaSPAdes
    + antiSMASH outputs but contain only what our parsers/metrics need."""
    replay_dir = workdir / "replay"
    replay_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}

    for sid in SAMPLES:
        # Synthetic contigs file (real bytes so artifact store gets a real hash).
        contigs = replay_dir / f"{sid}.contigs.fasta"
        with contigs.open("w") as fh:
            for i in range(5):
                fh.write(f">{sid}_contig_{i}\n")
                fh.write("ACGT" * 1500 + "\n")  # 6 kb each
        manifest[f"asm.metaspades.s_for_{sid}"] = {
            "tool_id": "assembly.metaspades",
            "output_paths": [str(contigs.relative_to(replay_dir))],
            "metrics": {
                "n_contigs": 5,
                "total_length": 5 * 6000,
                "n50": 6000,
                "largest_contig": 6000,
            },
        }
    manifest_path = replay_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return manifest_path


def _step_id_for_sample(sample_id: str) -> str:
    """Mirror IngestionAgent._sample_id hashing to predict step ids."""
    from hyphae.ids import short_hash

    return f"asm.metaspades.S_{short_hash('local_fastq', sample_id)}"


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
        # Record both possible assembler step IDs so the AssemblyAgent's
        # choice is tolerated by the manifest.
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
    assert len(final.samples) == len(SAMPLES)
    # All samples should at least reach assembly via replay.
    assert len(final.assemblies) == len(SAMPLES)
    # MAG records should be created (placeholder-from-contigs path) for every
    # sample whose assembly produced contigs.
    assert len(final.mags) == len(SAMPLES)
    # No real antismash, so 0 BGCs — and the rationales should say so.
    bgc_skipped = [r for r in final.rationales if r.producer_agent == "bgc_discovery"]
    assert any("deferred" in r.claim or "failed" in r.claim for r in bgc_skipped)


def test_junttila_benchmark_scores_replay_run(tmp_path: Path, fastq_root: Path) -> None:
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
    hrun, initial = make_run(
        workdir, Intent(sample_sources=sources), replay_manifest=manifest, deterministic=True
    )
    final = Coordinator(hrun.context()).run(initial).final_state

    bench = Junttila2021Benchmark()
    result = bench.evaluate(final)
    # Replay-only (no BGCs, no BUSCO) -> we expect the harness to register
    # failures rather than crash. This proves the wiring: Hyphae produces
    # numbers the benchmark can score against.
    assert result.benchmark_id == "junttila2021"
    assert result.n_total > 0
    # The "all samples assembled" check should pass.
    pass_names = {r.check.name for r in result.metric_results if r.passed}
    assert "total_samples_assembled" in pass_names
