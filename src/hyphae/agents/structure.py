"""Deterministic scaffold inference from BGC domain architecture."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..ids import new_rationale_id, short_hash
from ..state import Rationale

if TYPE_CHECKING:
    from ..runtime.deterministic_executor import Manifest


class StructureInferenceAgent:
    """Generate transparent scaffold hypotheses without invoking chemistry tools."""

    def infer(self, manifest: Manifest, use_antismash: bool = False) -> Manifest:
        """Infer scaffolds, using antiSMASH annotations when explicitly enabled.

        Network/API failures are deliberately contained: every BGC still gets
        the same deterministic domain-based fallback used in offline mode.
        """
        bgcs = manifest.final_state.get("bgcs", [])
        structures = manifest.final_state.setdefault("structures", [])
        if not isinstance(structures, list):
            structures = []
            manifest.final_state["structures"] = structures

        for bgc in sorted(bgcs, key=self._novelty, reverse=True):
            record = self._record(bgc)
            domains, confidence, source = self._domains_and_confidence(record, use_antismash)
            scaffold_type = self._scaffold_type(record["type"], domains)
            if scaffold_type == "ribosomal":
                claim = f"Deferred {record['id']}: ribosomal BGC scaffold inference needs sequence context."
                manifest.rationales.append(self._rationale(claim))
                continue
            candidates = self._candidate_smiles(record["id"], scaffold_type)
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
                    "source": source,
                })
            claim = (
                f"Inferred 3 {scaffold_type} scaffold candidates from {len(domains)} domains; "
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
        }

    def _domains_and_confidence(
        self, bgc: dict[str, Any], use_antismash: bool
    ) -> tuple[list[str], float, str]:
        if use_antismash and bgc.get("contig_path"):
            try:
                import requests

                fasta_content = Path(str(bgc["contig_path"])).read_text()
                response = requests.post(
                    "https://antismash.secondarymetabolites.org/api/v1/submit",
                    files={"sequence": ("contig.fasta", fasta_content, "text/plain")},
                    timeout=30,
                )
                if response.status_code == 200:
                    job_id = response.json()["submission_id"]
                    result = requests.get(
                        f"https://antismash.secondarymetabolites.org/api/v1/results/{job_id}",
                        timeout=60,
                    )
                    if result.status_code == 200:
                        domains = self._extract_domains_from_antismash(result.json())
                        return domains, 0.85, "antismash"
            except Exception:
                pass
        domains, confidence = self._heuristic_domains(bgc)
        return domains, confidence, "heuristic"

    @staticmethod
    def _extract_domains_from_antismash(antismash_json: dict[str, Any]) -> list[str]:
        """Extract CDS-motif names from the compact antiSMASH API response."""
        domains = [
            str(motif.get("note", "unknown"))
            for cluster in antismash_json.get("clusters", [])
            for motif in cluster.get("cds_motifs", [])
            if isinstance(motif, dict)
        ]
        return domains or ["unknown"]

    @staticmethod
    def _heuristic_domains(bgc: dict[str, Any]) -> tuple[list[str], float]:
        domains = list(bgc.get("domains") or ["unknown"])
        scaffold = StructureInferenceAgent._scaffold_type(str(bgc.get("type", "other")), domains)
        return domains, StructureInferenceAgent._confidence(scaffold, len(domains))

    def _generate_smiles_candidates(self, domains: list[str], bgc_id: str = "domains") -> list[str]:
        """Compatibility helper for callers that start from domain annotations."""
        scaffold = self._scaffold_type("other", [str(domain).upper() for domain in domains])
        return self._candidate_smiles(bgc_id, scaffold)

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
    def _confidence(scaffold_type: str, domain_count: int) -> float:
        if scaffold_type in {"linear peptide", "polyketide"}:
            return 0.9 if domain_count > 5 else 0.8
        return min(0.95, 0.5 + domain_count * 0.05)

    @staticmethod
    def _candidate_smiles(bgc_id: str, scaffold_type: str) -> list[str]:
        """Return base, X-modified, and Y-modified valid-SMILES-like candidates."""
        templates = {
            "linear peptide": "NCC(=O)NCC(=O)O",
            "polyketide": "CC(=O)CC(=O)O",
            "hybrid": "NCC(=O)CC(=O)O",
        }
        base = templates[scaffold_type]
        digest = hashlib.sha256(bgc_id.encode()).hexdigest()
        modification_x = "c1ccccc1" if int(digest[:2], 16) % 2 else "C"
        modification_y = "Cl" if int(digest[2:4], 16) % 2 else "O"
        return [base, base + modification_x, base + modification_y]

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
