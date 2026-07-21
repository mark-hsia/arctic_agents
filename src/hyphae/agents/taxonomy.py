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
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..ids import new_rationale_id
from ..state import RunState, RunStatePatch, TaxonomyCall
from .species_predictor import GenomeComparator
from .base import Agent, AgentContext

if TYPE_CHECKING:
    from ..runtime.deterministic_executor import Manifest


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

    def analyze(self, manifest: Manifest, target_pathogen: str) -> Manifest:
        """Assign coarse taxonomy from assembly quality and target-name evidence.

        This is deliberately a decision layer, not a substitute for Kraken2 or
        GTDB-Tk.  It emits an auditable provisional call that later tools may
        replace.
        """
        assemblies = manifest.final_state.get("assemblies", {})
        if not isinstance(assemblies, dict):
            return manifest
        taxonomy = manifest.final_state.setdefault("taxonomy", {})
        if not isinstance(taxonomy, dict):
            taxonomy = {}
            manifest.final_state["taxonomy"] = taxonomy

        for sample_id, reference in assemblies.items():
            path = self._assembly_path(manifest, reference)
            if path is None or not path.is_file():
                continue
            stats = GenomeComparator().compare(path)
            contigs = int(stats["n_contigs"])
            n50 = int(stats["n50"])
            mean_depth = self._mean_read_depth(path)
            confidence = 0.6
            quality = "moderate-quality assembly"
            if n50 > 50_000 and contigs < 200:
                confidence = 0.85
                quality = "high-quality fungal-MAG-like assembly"
            elif n50 < 10_000 or contigs > 1_000:
                confidence = 0.4
                quality = "fragmented or potentially contaminated assembly"

            target_match = self._target_match(path, target_pathogen)
            if target_match:
                confidence = min(0.95, confidence + 0.1)
            taxid = target_pathogen if target_match else "unknown"
            claim = (
                f"Assigned taxonomy for {sample_id} from {quality} "
                f"(N50={n50}, contigs={contigs}, mean_depth={mean_depth}); "
                f"target match={target_match}."
            )
            rationale_id = new_rationale_id("taxonomy", claim, deterministic=True)
            taxonomy[str(sample_id)] = {
                "taxid": taxid,
                "confidence": confidence,
                "rationale_id": rationale_id,
            }
            manifest.rationales.append(self._manifest_rationale(rationale_id, claim))
        return manifest

    @staticmethod
    def _assembly_path(manifest: Manifest, reference: Any) -> Path | None:
        if hasattr(reference, "assembly_artifact_id"):
            reference = reference.assembly_artifact_id
        elif isinstance(reference, dict):
            reference = reference.get("assembly_artifact_id") or reference.get("path")
        artifacts = {artifact.artifact_id: artifact for artifact in manifest.artifacts}
        if reference in artifacts:
            reference = artifacts[reference].path
        return Path(str(reference)) if reference else None

    @staticmethod
    def _target_match(path: Path, target_pathogen: str) -> bool:
        target = target_pathogen.replace("_", " ").lower()
        if target.replace(" ", "_") in path.name.lower() or target in path.name.lower():
            return True
        with path.open(errors="replace") as handle:
            return any(target in line.lower() for _, line in zip(range(100), handle) if line.startswith(">"))

    @staticmethod
    def _mean_read_depth(path: Path) -> float | None:
        """Read optional ``depth=``/``cov=`` values embedded in FASTA headers."""
        depths: list[float] = []
        with path.open(errors="replace") as handle:
            for line in handle:
                if not line.startswith(">"):
                    continue
                match = re.search(r"(?:depth|cov)[=_:]([0-9]+(?:\.[0-9]+)?)", line, re.I)
                if match:
                    depths.append(float(match.group(1)))
        return round(sum(depths) / len(depths), 3) if depths else None

    @staticmethod
    def _manifest_rationale(rationale_id: str, claim: str):
        from ..state import Rationale

        return Rationale(rationale_id=rationale_id, producer_agent="taxonomy", claim=claim)

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


def analyze_and_discover(manifest: Manifest, target_pathogen: str) -> Manifest:
    """Run the deterministic taxonomy and synthetic-BGC decision layer."""
    from .bgc_discovery import BGCDiscoveryAgent

    manifest = TaxonomyAgent().analyze(manifest, target_pathogen)
    return BGCDiscoveryAgent().discover(manifest)
