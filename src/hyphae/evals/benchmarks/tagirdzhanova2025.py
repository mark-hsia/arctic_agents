"""Benchmark: Tagirdzhanova et al. 2025 — *Cladonia rangiformis* reference metagenome.

Reference:
  Tagirdzhanova G et al.
  "A reference metagenome sequence of the lichen *Cladonia rangiformis*."
  *BMC Biology* 23:... (2025).

This benchmark is a **named-BGC recovery** test: the paper reports a high-
quality reference metagenome with named BGCs in the mycobiont, including
grayanic acid, 6-hydroxymellein, FR901512, and clavaric acid. Outperforming
means recovering the named BGCs AND additional well-supported orphan BGCs.
"""

from __future__ import annotations

import json
from importlib import resources

from ...state import RunState
from ..metrics import named_bgc_recovery
from .base import Benchmark, Direction, MetricCheck


def load_paper_data() -> dict:
    with resources.files("hyphae.evals.benchmarks.data").joinpath(
        "tagirdzhanova2025.json"
    ).open() as fh:
        return json.load(fh)


def _named_recovery_extractor(name: str):
    def extractor(state: RunState) -> float | None:
        if not state.bgcs:
            return None
        rec = named_bgc_recovery(state, [name])
        return 1.0 if rec[name] else 0.0
    return extractor


class Tagirdzhanova2025Benchmark(Benchmark):
    benchmark_id = "tagirdzhanova2025"
    paper_reference = (
        "Tagirdzhanova et al. 2025 — Reference metagenome of *Cladonia rangiformis* "
        "(BMC Biology)"
    )
    paper_doi = "10.1186/s12915-025-02428-z"

    def expected(self) -> list[MetricCheck]:
        data = load_paper_data()
        names: list[str] = data["named_mycobiont_bgcs"]
        checks = [
            MetricCheck(
                name=f"named_bgc_recovery::{name}",
                stage="bgc_discovery",
                direction=Direction.at_least,
                paper_value=1.0,
                extractor=_named_recovery_extractor(name),
                description=f"Recover BGC for {name} (named in paper).",
            )
            for name in names
        ]
        checks.append(
            MetricCheck(
                name="total_bgcs_at_least_paper",
                stage="bgc_discovery",
                direction=Direction.at_least,
                paper_value=data["paper_total_bgcs"],
                extractor=lambda s: float(len(s.bgcs)),
                description="Total BGCs at least paper count.",
            )
        )
        return checks

    def inputs(self) -> dict:
        data = load_paper_data()
        return {
            "sample_kind": "pacbio_hifi",
            "expected_named_bgcs": data["named_mycobiont_bgcs"],
        }
