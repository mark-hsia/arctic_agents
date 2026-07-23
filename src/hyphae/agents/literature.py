"""Cache-backed literature linking for manifest claims."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..knowledge import KnowledgeBase
from ..state import Citation, RunState, RunStatePatch
from .base import Agent, AgentContext
from ..guard import validate_output
if TYPE_CHECKING:
    from ..runtime.deterministic_executor import Manifest


class LiteratureAgent(Agent):
    """Cite only supplied knowledge-cache records; never performs web retrieval."""

    name = "literature"
    reads = ("bgcs", "structures", "docking", "artifacts")
    writes = ("literature",)
    tools = ()

    @validate_output
    def step(self, state: RunState, ctx: AgentContext) -> RunStatePatch:
        literature: dict[str, list[Citation]] = {}
        rationales = []
        artifact_ids = {artifact.artifact_id for artifact in state.artifacts}
        kb = KnowledgeBase()
        for bgc in state.bgcs:
            record = kb.lookup_bgc(bgc.bgc_id)
            evidence = [bgc.gbk_artifact_id] if bgc.gbk_artifact_id in artifact_ids else []
            if record:
                citation = Citation(
                    bgc_or_compound_id=bgc.bgc_id,
                    title=str(record.get("title") or record.get("product") or "MIBiG record"),
                    doi=record.get("doi"), url=record.get("url"), year=record.get("year"),
                )
                literature[bgc.bgc_id] = [citation]
                rationales.append(ctx.make_rationale(self.name, f"BGC {bgc.bgc_id} has an exact local MIBiG cache match.", evidence))
            else:
                rationale = ctx.make_rationale(self.name, f"BGC {bgc.bgc_id} has no exact local MIBiG cache match; novelty remains unknown.", evidence)
                rationale.accepted = False
                rationales.append(rationale)
        ctx.record(rationales=rationales)
        patch = RunStatePatch(literature=literature or None, rationales=rationales or None)
        self.validate_patch(patch)
        return patch

    def cite(
        self,
        manifest: Manifest,
        knowledge_cache: dict[str, Any] | KnowledgeBase | None = None,
        knowledge_base: KnowledgeBase | None = None,
    ) -> Manifest:
        """Attach cache citations and flag exact ChEMBL structure matches."""
        if isinstance(knowledge_cache, KnowledgeBase):
            knowledge_base = knowledge_cache
            knowledge_cache = None
        kb = knowledge_base or KnowledgeBase()
        cache = knowledge_cache or {}
        literature = manifest.final_state.setdefault("literature", [])
        if not isinstance(literature, list):
            literature = []
            manifest.final_state["literature"] = literature
        smiles_by_rationale = self._smiles_by_rationale(manifest)
        for structure in manifest.final_state.get("structures", []):
            if hasattr(structure, "model_dump"):
                structure = structure.model_dump()
            if not isinstance(structure, dict):
                continue
            smiles = structure.get("smiles")
            chembl_hit = kb.lookup_smiles(str(smiles)) if smiles else None
            if chembl_hit:
                literature.append({
                    "claim_id": structure.get("rationale_id", structure.get("structure_id")),
                    "citations": [{
                        "source": "ChEMBL",
                        "claim": f"Compound already characterized: {chembl_hit.get('target', 'unknown target')}",
                        "relevance": 0.9,
                    }],
                    "evidence_artifact_ids": [],
                })
                structure["novelty_flag"] = "prior_art"
        for rationale in manifest.rationales:
            claim = rationale.claim
            citations = self._matches(claim, cache)
            comments: list[str] = []
            if "novel" in claim.lower():
                matching_smiles = smiles_by_rationale.get(rationale.rationale_id, [])
                if self._has_prior_art(matching_smiles, cache) or any(
                    kb.lookup_smiles(smiles) for smiles in matching_smiles
                ):
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
