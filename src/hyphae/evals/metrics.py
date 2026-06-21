"""Metric implementations.

These are pure functions over :class:`hyphae.state.RunState` (or simpler
inputs) so they can be unit-tested without any bio tooling.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable

from ..state import BGC, MAG, BGCClass, RunState

# --------------------------------------------------------------------------- #
# Assembly-level metrics
# --------------------------------------------------------------------------- #


def assembly_metrics(state: RunState) -> dict[str, dict[str, float]]:
    """Return ``{sample_id: {n50, total_length, n_contigs}}``."""
    out: dict[str, dict[str, float]] = {}
    for sid, asm in state.assemblies.items():
        out[sid] = {
            "n50": float(asm.n50 or 0),
            "total_length": float(asm.total_length or 0),
            "n_contigs": float(asm.n_contigs or 0),
            "largest_contig": float(asm.largest_contig or 0),
        }
    return out


# --------------------------------------------------------------------------- #
# MAG-level metrics
# --------------------------------------------------------------------------- #


def mag_quality_summary(state: RunState) -> dict[str, dict[str, float | None]]:
    """Per-MAG summary of completeness, contamination, BUSCO."""
    return {
        m.mag_id: {
            "completeness": m.completeness,
            "contamination": m.contamination,
            "busco_complete": m.busco_complete,
        }
        for m in state.mags
    }


def busco_completeness_distribution(state: RunState) -> dict[str, float]:
    vals = [m.busco_complete for m in state.mags if m.busco_complete is not None]
    if not vals:
        return {"n": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0}
    return {
        "n": float(len(vals)),
        "mean": sum(vals) / len(vals),
        "min": min(vals),
        "max": max(vals),
    }


# --------------------------------------------------------------------------- #
# BGC-level metrics
# --------------------------------------------------------------------------- #


def bgc_count_by_sample(state: RunState) -> dict[str, int]:
    sample_for_mag = {m.mag_id: m.sample_id for m in state.mags}
    counts: dict[str, int] = defaultdict(int)
    for bgc in state.bgcs:
        sid = sample_for_mag.get(bgc.mag_id)
        if sid:
            counts[sid] += 1
    return dict(counts)


def bgc_class_distribution(state: RunState, sample_id: str | None = None) -> dict[BGCClass, int]:
    sample_for_mag = {m.mag_id: m.sample_id for m in state.mags}
    iterable: Iterable[BGC] = state.bgcs
    if sample_id is not None:
        iterable = [b for b in state.bgcs if sample_for_mag.get(b.mag_id) == sample_id]
    return dict(Counter(b.bgc_class for b in iterable))


def t1pks_count_by_sample(state: RunState) -> dict[str, int]:
    sample_for_mag = {m.mag_id: m.sample_id for m in state.mags}
    counts: dict[str, int] = defaultdict(int)
    for bgc in state.bgcs:
        if bgc.bgc_class != BGCClass.t1pks:
            continue
        sid = sample_for_mag.get(bgc.mag_id)
        if sid:
            counts[sid] += 1
    return dict(counts)


def orphan_bgc_fraction(state: RunState) -> float:
    if not state.gcfs:
        return float("nan")
    orphan_members = sum(len(g.member_bgc_ids) for g in state.gcfs if g.is_orphan)
    total = sum(len(g.member_bgc_ids) for g in state.gcfs) or 1
    return orphan_members / total


# --------------------------------------------------------------------------- #
# Named-BGC recovery
# --------------------------------------------------------------------------- #


_NAMING_NORM_RE = re.compile(r"[^a-z0-9]")


def _norm(name: str) -> str:
    return _NAMING_NORM_RE.sub("", name.lower())


def named_bgc_recovery(state: RunState, expected_names: list[str]) -> dict[str, bool]:
    """Loose substring match against ``BGC.product`` / ``domains`` / ``bgc_id``.

    A real implementation will eventually compare against MIBiG GCF
    membership; substring is a defensible v0 because the benchmark papers
    report named compounds as natural-language strings.
    """
    found: dict[str, bool] = {name: False for name in expected_names}
    for bgc in state.bgcs:
        haystack = " ".join(
            [
                _norm(bgc.product or ""),
                _norm(" ".join(bgc.domains)),
                _norm(bgc.bgc_id),
            ]
        )
        for name in expected_names:
            if _norm(name) and _norm(name) in haystack:
                found[name] = True
    return found


# --------------------------------------------------------------------------- #
# Diversity (ecology summary)
# --------------------------------------------------------------------------- #


def fungal_shannon_per_sample(state: RunState) -> dict[str, float]:
    by_sample: dict[str, list[MAG]] = defaultdict(list)
    for m in state.mags:
        if m.is_fungal:
            by_sample[m.sample_id].append(m)
    out: dict[str, float] = {}
    for sid, mags in by_sample.items():
        labels = []
        for m in mags:
            tax = state.taxonomy.get(m.mag_id)
            labels.append(
                tax.genus or tax.family or tax.phylum if tax else "unknown"
            )
        counts = list(Counter(labels).values())
        total = sum(counts) or 1
        h = 0.0
        for c in counts:
            if c == 0:
                continue
            p = c / total
            h -= p * math.log(p)
        out[sid] = h
    return out
