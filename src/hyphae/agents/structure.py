"""Deterministic scaffold inference from BGC domain architecture."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..ids import new_rationale_id, short_hash
from ..state import BGC, InferredStructure, Rationale, RunState, RunStatePatch
from .base import Agent, AgentContext
from ..guard import validate_output

if TYPE_CHECKING:
    from ..runtime.deterministic_executor import Manifest


class StructureInferenceAgent(Agent):
    """Register only externally supplied, provenance-bearing structure calls."""

    name = "structure"
    reads = ("bgcs", "novelty", "artifacts")
    writes = ("structures",)
    tools = ()

    @validate_output
    def step(self, state: RunState, ctx: AgentContext) -> RunStatePatch:
        """Promote only BGC structures backed by a registered GBK/provider artifact.

        Pfam domain class alone cannot determine an exact molecular structure;
        producing a template SMILES would be fabricated evidence.
        """
        structures: dict[str, list[InferredStructure]] = {}
        rationales: list[Rationale] = []
        known_artifacts = {artifact.artifact_id for artifact in state.artifacts}
        for bgc in state.bgcs:
            evidence_id = bgc.gbk_artifact_id
            if evidence_id is None or evidence_id not in known_artifacts:
                rationale = ctx.make_rationale(
                    self.name,
                    f"Structure inference for {bgc.bgc_id} deferred: domain architecture does not identify an exact SMILES without a provenance-bearing predictor artifact.",
                    [evidence_id] if evidence_id else [],
                )
                rationale.accepted = False
                rationales.append(rationale)
                continue
            rationale = ctx.make_rationale(
                self.name,
                f"Structure inference for {bgc.bgc_id} deferred: no externally supplied structure-prediction result was registered.",
                [evidence_id],
            )
            rationale.accepted = False
            rationales.append(rationale)
        ctx.record(rationales=rationales)
        patch = RunStatePatch(structures=structures or None, rationales=rationales or None)
        self.validate_patch(patch)
        return patch

    def infer(self, manifest: Manifest, use_antismash: bool = False) -> Manifest:
        """Create structures only from real BGC-associated SMILES annotations.

        antiSMASH provides domain architecture but generally does *not* infer
        chemical structures. A structure-prediction provider must therefore
        attach ``smiles`` to a BGC before this stage can proceed.
        """
        if not use_antismash:
            raise RuntimeError(
                "Real structure inference requires use_antismash=True and a configured "
                "structure-prediction provider; heuristic SMILES generation is disabled."
            )
        bgcs = manifest.final_state.get("bgcs", [])
        structures = manifest.final_state.setdefault("structures", [])
        if not isinstance(structures, list):
            structures = []
            manifest.final_state["structures"] = structures

        for bgc in sorted(bgcs, key=self._novelty, reverse=True):
            record = self._record(bgc)
            domains = record["domains"]
            confidence = float(record.get("confidence", 0.0))
            scaffold_type = self._scaffold_type(record["type"], domains)
            candidates = record["smiles"]
            if not candidates:
                raise RuntimeError(
                    f"No experimentally or model-derived SMILES for BGC {record['id']}. "
                    "Configure a structure-prediction provider and attach its provenance-bearing "
                    "SMILES output before docking."
                )
            candidates = [candidates] if isinstance(candidates, str) else list(candidates)
            candidate_ids: list[str] = []
            for index, smiles in enumerate(candidates, start=1):
                structure_id = f"STR_{short_hash(record['id'], str(index), smiles)}"
                candidate_ids.append(structure_id)
                structures.append({
                    "structure_id": structure_id,
                    "bgc_id": record["id"],
                    "smiles": smiles,
                    "confidence": round(max(0.0, min(1.0, confidence - (index - 1) * 0.04)), 3),
                    "scaffold_type": scaffold_type,
                    "source": str(record.get("structure_source", "external_structure_predictor")),
                })
            claim = (
                f"Registered {len(candidates)} {scaffold_type} structure candidates from {len(domains)} domains; "
                f"top confidence={confidence:.2f}."
            )
            rationale = self._rationale(claim)
            manifest.rationales.append(rationale)
            for structure in structures[-3:]:
                if structure["structure_id"] in candidate_ids:
                    structure["rationale_id"] = rationale.rationale_id
        return manifest

    @staticmethod
    def _record(bgc: Any) -> dict[str, Any]:
        if hasattr(bgc, "model_dump"):
            bgc = bgc.model_dump()
        if not isinstance(bgc, dict):
            bgc = {"bgc_id": str(bgc)}
        return {
            "id": str(bgc.get("bgc_id", bgc.get("id", "unknown_bgc"))),
            "type": str(bgc.get("type", bgc.get("bgc_class", bgc.get("product", "other")))).lower(),
            "domains": [str(domain).upper() for domain in bgc.get("domains", [])],
            "novelty_score": float(bgc.get("novelty_score", 0.0)),
            "contig_path": bgc.get("contig_path"),
            "smiles": bgc.get("smiles", []),
            "confidence": float(bgc.get("confidence", 0.0)),
            "structure_source": bgc.get("structure_source"),
        }

    @staticmethod
    def _novelty(bgc: Any) -> float:
        return StructureInferenceAgent._record(bgc)["novelty_score"]

    @staticmethod
    def _scaffold_type(bgc_type: str, domains: list[str]) -> str:
        domain_set = set(domains)
        if "RIPP" in bgc_type.upper() or "BACTERIOCIN" in bgc_type.upper():
            return "ribosomal"
        if "HYBRID" in bgc_type.upper() or ({"A", "PCP", "C"} & domain_set and {"AT", "TE"} & domain_set):
            return "hybrid"
        if {"PCP", "C"}.issubset(domain_set) or "NRPS" in bgc_type.upper():
            return "linear peptide"
        if {"AT", "TE"}.issubset(domain_set) or "PKS" in bgc_type.upper():
            return "polyketide"
        return "hybrid"

    @staticmethod
    def _rationale(claim: str) -> Rationale:
        return Rationale(
            rationale_id=new_rationale_id("structure_inference", claim, deterministic=True),
            producer_agent="structure_inference",
            claim=claim,
        )


def infer_and_dock(manifest: Manifest, target_pack: dict[str, Any]) -> Manifest:
    """Run deterministic structure inference followed by ranking-only docking."""
    from .docking import TargetDockingAgent

    manifest = StructureInferenceAgent().infer(manifest)
    return TargetDockingAgent().dock(manifest, target_pack)
