"""Benchmark: Lee et al. 2024 — comparative genomics of six *Cladonia* species.

Reference:
  Lee et al.
  "Comparative genomics of *Cladonia* species reveals secondary metabolite
  diversity and putative environmental adaptations."
  *Scientific Reports* 14: ... (2024). DOI 10.1038/s41598-024-51895-x

Per-species BGC counts via antiSMASH fungal v7.0:
  C. borealis      33
  C. grayi         27
  C. macilenta     31
  C. metacorallifera 36
  C. rangiferina   35
  C. uncialis      28

This benchmark is a **per-species ceiling**. Hyphae's mycobiont MAG for any
of these species should land at most ~10 % below the per-species count and
ideally above it once we add tool ensembling (DeepBGC + GECCO).
"""

from __future__ import annotations

import json
from importlib import resources

from ...state import RunState
from .base import Benchmark, Direction, MetricCheck


def load_paper_data() -> dict:
    with resources.files("hyphae.evals.benchmarks.data").joinpath(
        "lee2024.json"
    ).open() as fh:
        return json.load(fh)


def _bgc_count_for_species(species: str):
    species_norm = species.lower().replace(" ", "_")

    def extractor(state: RunState) -> float | None:
        # Identify MAGs whose taxonomy.species matches.
        target_mag_ids = set()
        for mag_id, tax in state.taxonomy.items():
            if tax.species and species_norm in tax.species.lower().replace(" ", "_"):
                target_mag_ids.add(mag_id)
        if not target_mag_ids:
            return None
        return float(sum(1 for b in state.bgcs if b.mag_id in target_mag_ids))

    return extractor


class Lee2024Benchmark(Benchmark):
    benchmark_id = "lee2024"
    paper_reference = (
        "Lee et al. 2024, Scientific Reports — Comparative genomics of six Cladonia "
        "species (antiSMASH fungal v7.0)"
    )
    paper_doi = "10.1038/s41598-024-51895-x"

    def expected(self) -> list[MetricCheck]:
        data = load_paper_data()
        out: list[MetricCheck] = []
        for species, count in data["per_species_bgc_count"].items():
            out.append(
                MetricCheck(
                    name=f"bgc_count::{species}",
                    stage="bgc_discovery",
                    direction=Direction.at_least,
                    paper_value=float(count),
                    extractor=_bgc_count_for_species(species),
                    tolerance=0.10,  # 10% slack — per-species ceiling, not floor
                    description=f"BGCs for {species} >= paper - 10%.",
                )
            )
        return out

    def inputs(self) -> dict:
        return {"reference_genomes": list(load_paper_data()["per_species_bgc_count"].keys())}
