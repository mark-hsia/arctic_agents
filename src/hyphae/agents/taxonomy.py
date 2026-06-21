"""Taxonomy & Ecology agent.

The Assembly agent already records a coarse taxonomy call when EukRep + BUSCO
are run. This agent's job is the *ecology* layer: per-sample fungal
diversity, co-occurrence summaries, and flagging samples interesting under the
platform's competition-drives-novelty hypothesis.

v0.1 emits Shannon diversity over fungal MAGs and a co-occurrence rationale
when a sample contains ≥ 2 fungal MAGs from distinct candidate genera.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict

from ..state import RunState, RunStatePatch, TaxonomyCall
from .base import Agent, AgentContext


def shannon(counts: list[int]) -> float:
    total = sum(counts)
    if total == 0:
        return 0.0
    h = 0.0
    for c in counts:
        if c == 0:
            continue
        p = c / total
        h -= p * math.log(p)
    return h


class TaxonomyAgent(Agent):
    name = "taxonomy"
    reads = ("mags", "taxonomy")
    writes = ("taxonomy",)
    tools = ()

    def step(self, state: RunState, ctx: AgentContext) -> RunStatePatch:
        new_taxonomy: dict[str, TaxonomyCall] = {}
        new_rationales = []

        per_sample: dict[str, list[TaxonomyCall]] = defaultdict(list)
        for mag in state.mags:
            call = state.taxonomy.get(mag.mag_id)
            if call is None and mag.is_fungal:
                call = TaxonomyCall(
                    mag_id=mag.mag_id,
                    domain="Eukaryota",
                    phylum="Ascomycota" if (mag.busco_complete or 0) > 50 else None,
                    method="EukRep+BUSCO_ascomycota",
                    confidence=(mag.busco_complete / 100) if mag.busco_complete else None,
                )
                new_taxonomy[mag.mag_id] = call
            if call is not None:
                per_sample[mag.sample_id].append(call)

        for sample_id, calls in per_sample.items():
            fungal = [c for c in calls if c.domain == "Eukaryota"]
            if not fungal:
                continue
            genera = [c.genus or c.family or c.phylum or "unknown" for c in fungal]
            counts = list(Counter(genera).values())
            h = shannon(counts)
            distinct = len(set(genera) - {"unknown"})
            claim = (
                f"Sample {sample_id}: {len(fungal)} fungal MAGs across "
                f"{len(set(genera))} taxonomic groups; Shannon={h:.3f}."
            )
            if distinct >= 2:
                claim += " Co-occurrence flag: hypothesis-of-interest (competition-driven novelty)."
            new_rationales.append(ctx.make_rationale(self.name, claim))

        ctx.record(rationales=new_rationales)
        patch = RunStatePatch(
            taxonomy=new_taxonomy or None,
            rationales=new_rationales or None,
        )
        self.validate_patch(patch)
        return patch
