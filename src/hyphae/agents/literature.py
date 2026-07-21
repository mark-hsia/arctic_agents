"""Cache-backed literature linking for manifest claims."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..runtime.deterministic_executor import Manifest


class LiteratureAgent:
    """Cite only supplied knowledge-cache records; never performs web retrieval."""

    def cite(self, manifest: Manifest, knowledge_cache: dict[str, Any]) -> Manifest:
        literature = manifest.final_state.setdefault("literature", [])
        if not isinstance(literature, list):
            literature = []
            manifest.final_state["literature"] = literature
        smiles_by_rationale = self._smiles_by_rationale(manifest)
        for rationale in manifest.rationales:
            claim = rationale.claim
            citations = self._matches(claim, knowledge_cache)
            comments: list[str] = []
            if "novel" in claim.lower():
                matching_smiles = smiles_by_rationale.get(rationale.rationale_id, [])
                if self._has_prior_art(matching_smiles, knowledge_cache):
                    comments.append("This 'novel' structure has prior art")
                    rationale.accepted = False
                elif not citations:
                    citations.append({"source": "MIBiG/ChEMBL negative cache check", "pmid": None, "relevance": 0.0})
            if not citations:
                comments.append("Exploratory claim: no matching cached citation")
            rationale.critic_comments.extend(comment for comment in comments if comment not in rationale.critic_comments)
            literature.append({
                "claim_id": rationale.rationale_id,
                "citations": citations,
                "evidence_artifact_ids": list(rationale.evidence_artifact_ids),
            })
        return manifest

    @staticmethod
    def _matches(claim: str, cache: dict[str, Any]) -> list[dict[str, Any]]:
        claim_lower = claim.lower()
        citations: list[dict[str, Any]] = []
        for key, records in cache.items():
            key_lower = key.lower()
            exact = key_lower in claim_lower
            partial = any(token in claim_lower for token in key_lower.replace("_", " ").split())
            if not (exact or partial):
                continue
            for record in records if isinstance(records, list) else []:
                if not isinstance(record, dict):
                    continue
                citations.append({
                    "source": record.get("title", key),
                    "pmid": record.get("pmid"),
                    "relevance": float(record.get("bgc_relevance", record.get("relevance", 1.0 if exact else 0.5))),
                })
        return citations

    @staticmethod
    def _smiles_by_rationale(manifest: Manifest) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for structure in manifest.final_state.get("structures", []):
            if hasattr(structure, "model_dump"):
                structure = structure.model_dump()
            if isinstance(structure, dict) and structure.get("rationale_id"):
                result.setdefault(str(structure["rationale_id"]), []).append(str(structure.get("smiles", "")))
        return result

    @staticmethod
    def _has_prior_art(smiles: list[str], cache: dict[str, Any]) -> bool:
        searchable = str(cache).lower()
        return any(smiles_value and smiles_value.lower() in searchable for smiles_value in smiles)
