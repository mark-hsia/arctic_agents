"""Benchmark: Junttila et al. 2021.

Reference:
  Junttila S, Eltahir AME, Brouwer H et al.
  "Microbial Communities of *Cladonia* Lichens and Their Biosynthetic Gene
  Clusters Potentially Encoding Natural Products."
  *Microorganisms* 9(7): 1347 (2021). DOI: 10.3390/microorganisms9071347

Why this is the primary benchmark:
  * Six public *Cladonia* metagenomes from Southern Finland (ENA PRJEB34718).
  * Reported per-sample numbers we can match: BUSCO Ascomycota completeness
    (91.5 - 93.6 %), 28 - 41 BGCs per sample (12 - 28 T1PKS).
  * fungiSMASH v6.0.0-alpha (web) + standalone antiSMASH v5.0.0; we'll match
    against fungiSMASH numbers since they are stricter.

Outperforming the paper (per-stage definitions):
  * MAG QC: more MAGs at >= 70 % completeness AND <= 10 % contamination.
  * BUSCO: each sample's per-MAG BUSCO Ascomycota >= the paper's per-sample.
  * BGC count: at least the paper's number AND a non-trivial novelty
    breakdown (the paper does not separate orphan vs. known beyond MIBiG hits).
  * T1PKS: match paper's lower bound (12) at minimum on every sample.

The numbers below are encoded as per-sample expectations + run-level summaries.
The paper's Table 1 entries are reproduced verbatim under
``data/benchmarks/junttila2021.json``.
"""

from __future__ import annotations

import json
from importlib import resources

from ...state import BGCClass, RunState
from .base import Benchmark, Direction, MetricCheck

SAMPLES = ["L1", "L2", "L3", "L4", "L34", "L35"]


def load_paper_table() -> dict:
    with resources.files("hyphae.evals.benchmarks.data").joinpath(
        "junttila2021.json"
    ).open() as fh:
        return json.load(fh)


def _bgc_count_for_sample(sample_id: str):
    def extractor(state: RunState) -> float | None:
        sample_for_mag = {m.mag_id: m.sample_id for m in state.mags}
        n = sum(1 for b in state.bgcs if sample_for_mag.get(b.mag_id) == sample_id)
        return float(n) if state.bgcs else None
    return extractor


def _t1pks_count_for_sample(sample_id: str):
    def extractor(state: RunState) -> float | None:
        sample_for_mag = {m.mag_id: m.sample_id for m in state.mags}
        n = sum(
            1
            for b in state.bgcs
            if sample_for_mag.get(b.mag_id) == sample_id and b.bgc_class == BGCClass.t1pks
        )
        return float(n) if state.bgcs else None
    return extractor


def _busco_for_sample(sample_id: str):
    def extractor(state: RunState) -> float | None:
        vals = [
            m.busco_complete
            for m in state.mags
            if m.sample_id == sample_id and m.busco_complete is not None
        ]
        if not vals:
            return None
        return max(vals)  # report the best fungal MAG per sample
    return extractor


class Junttila2021Benchmark(Benchmark):
    benchmark_id = "junttila2021"
    paper_reference = (
        "Junttila et al. 2021, Microorganisms 9:1347 — Cladonia lichen metagenomes "
        "(ENA PRJEB34718)"
    )
    paper_doi = "10.3390/microorganisms9071347"

    def expected(self) -> list[MetricCheck]:
        table = load_paper_table()
        per_sample: dict[str, dict[str, float]] = table["per_sample"]
        checks: list[MetricCheck] = []

        for sid in SAMPLES:
            entry = per_sample[sid]
            checks.append(
                MetricCheck(
                    name=f"busco_ascomycota_complete_{sid}",
                    stage="mag_qc",
                    direction=Direction.at_least,
                    paper_value=entry["busco_ascomycota_complete"],
                    extractor=_busco_for_sample(sid),
                    units="%",
                    description=f"BUSCO Ascomycota complete % on best fungal MAG of {sid}.",
                )
            )
            checks.append(
                MetricCheck(
                    name=f"bgc_count_{sid}",
                    stage="bgc_discovery",
                    direction=Direction.at_least,
                    paper_value=entry["bgc_count_fungismash"],
                    extractor=_bgc_count_for_sample(sid),
                    description=f"Total BGCs (fungiSMASH) on {sid}.",
                )
            )
            checks.append(
                MetricCheck(
                    name=f"t1pks_count_{sid}",
                    stage="bgc_discovery",
                    direction=Direction.at_least,
                    paper_value=entry["t1pks_count_fungismash"],
                    extractor=_t1pks_count_for_sample(sid),
                    description=f"T1PKS BGCs on {sid}.",
                )
            )

        # Run-level summary checks.
        checks.append(
            MetricCheck(
                name="total_samples_assembled",
                stage="assembly",
                direction=Direction.at_least,
                paper_value=6,
                extractor=lambda s: float(len(s.assemblies)),
                description="All six Junttila samples assembled.",
            )
        )
        checks.append(
            MetricCheck(
                name="total_bgcs",
                stage="bgc_discovery",
                direction=Direction.at_least,
                paper_value=table["paper_total_bgcs_lower"],
                extractor=lambda s: float(len(s.bgcs)),
                description="Sum of BGCs across all samples >= paper lower bound.",
            )
        )
        return checks

    def inputs(self) -> dict:
        table = load_paper_table()
        return {
            "ena_project": "PRJEB34718",
            "samples": SAMPLES,
            "per_sample_accessions": table.get("per_sample_accessions", {}),
        }
