"""Unit tests for benchmark scoring logic against constructed RunStates."""

from __future__ import annotations

from hyphae.evals.benchmarks import (
    Junttila2021Benchmark,
    Lee2024Benchmark,
    Tagirdzhanova2025Benchmark,
)
from hyphae.evals.benchmarks.junttila2021 import SAMPLES, load_paper_table
from hyphae.evals.benchmarks.tagirdzhanova2025 import load_paper_data as load_tagirdzhanova
from hyphae.evals.report import render_combined_markdown, render_markdown
from hyphae.state import (
    BGC,
    MAG,
    AssemblyResult,
    BGCClass,
    Intent,
    RunState,
    TaxonomyCall,
)


def _state_for_junttila_with_counts(per_sample: dict[str, tuple[int, int, float]]) -> RunState:
    """``per_sample`` -> ``(total_bgcs, t1pks, busco%)``."""
    mags: list[MAG] = []
    bgcs: list[BGC] = []
    assemblies: dict[str, AssemblyResult] = {}
    for sid, (total, t1pks, busco) in per_sample.items():
        mag_id = f"M_{sid}"
        mags.append(
            MAG(
                mag_id=mag_id,
                sample_id=sid,
                binner="metabat2",
                fasta_artifact_id="a",
                busco_complete=busco,
                busco_lineage="ascomycota_odb10",
                is_fungal=True,
            )
        )
        assemblies[sid] = AssemblyResult(
            sample_id=sid, assembler="metaspades", assembly_artifact_id="a"
        )
        for i in range(total):
            bgcs.append(
                BGC(
                    bgc_id=f"B_{sid}_{i}",
                    mag_id=mag_id,
                    contig="c",
                    start=i * 1000,
                    end=i * 1000 + 500,
                    bgc_class=BGCClass.t1pks if i < t1pks else BGCClass.terpene,
                )
            )
    return RunState(
        run_id="r",
        intent=Intent(),
        assemblies=assemblies,
        mags=mags,
        bgcs=bgcs,
    )


def test_junttila_benchmark_passes_when_we_match_paper_exactly() -> None:
    table = load_paper_table()
    per_sample = {
        sid: (
            int(table["per_sample"][sid]["bgc_count_fungismash"]),
            int(table["per_sample"][sid]["t1pks_count_fungismash"]),
            float(table["per_sample"][sid]["busco_ascomycota_complete"]),
        )
        for sid in SAMPLES
    }
    state = _state_for_junttila_with_counts(per_sample)
    result = Junttila2021Benchmark().evaluate(state)
    failed = [r.check.name for r in result.metric_results if not r.passed]
    assert failed == [], f"unexpected failures: {failed}"


def test_junttila_benchmark_flags_below_paper() -> None:
    per_sample = {sid: (1, 0, 50.0) for sid in SAMPLES}
    state = _state_for_junttila_with_counts(per_sample)
    result = Junttila2021Benchmark().evaluate(state)
    assert result.n_passed < result.n_total


def test_tagirdzhanova_named_recovery() -> None:
    data = load_tagirdzhanova()
    names: list[str] = data["named_mycobiont_bgcs"]
    mag = MAG(mag_id="M1", sample_id="S1", binner="metabat2", fasta_artifact_id="a", is_fungal=True)
    bgcs = [
        BGC(
            bgc_id=f"BGC_{i}",
            mag_id="M1",
            contig="c",
            start=0,
            end=10,
            bgc_class=BGCClass.t1pks,
            product=name,
        )
        for i, name in enumerate(names)
    ]
    state = RunState(
        run_id="r",
        intent=Intent(),
        mags=[mag],
        bgcs=bgcs,
        assemblies={"S1": AssemblyResult(sample_id="S1", assembler="metaspades", assembly_artifact_id="a")},
    )
    result = Tagirdzhanova2025Benchmark().evaluate(state)
    name_passes = [r for r in result.metric_results if "named_bgc_recovery" in r.check.name]
    assert all(r.passed for r in name_passes)


def test_lee_benchmark_uses_taxonomy_species() -> None:
    state = RunState(
        run_id="r",
        intent=Intent(),
        mags=[MAG(mag_id="Mb", sample_id="S1", binner="metabat2", fasta_artifact_id="a")],
        taxonomy={"Mb": TaxonomyCall(mag_id="Mb", species="C. borealis")},
        bgcs=[
            BGC(bgc_id=f"B{i}", mag_id="Mb", contig="c", start=0, end=10, bgc_class=BGCClass.t1pks)
            for i in range(33)
        ],
        assemblies={"S1": AssemblyResult(sample_id="S1", assembler="metaspades", assembly_artifact_id="a")},
    )
    result = Lee2024Benchmark().evaluate(state)
    borealis = next(r for r in result.metric_results if "C. borealis" in r.check.name)
    assert borealis.passed


def test_render_markdown_smoke() -> None:
    state = _state_for_junttila_with_counts({sid: (1, 0, 50.0) for sid in SAMPLES})
    result = Junttila2021Benchmark().evaluate(state)
    md = render_markdown(result)
    assert "junttila2021" in md
    combined = render_combined_markdown(
        [Junttila2021Benchmark().evaluate(state)]
    )
    assert "Combined score" in combined
