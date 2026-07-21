"""Deterministic ranking-only docking heuristic."""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING, Any

from ..ids import new_rationale_id
from ..state import Rationale

if TYPE_CHECKING:
    from ..runtime.deterministic_executor import Manifest


class TargetDockingAgent:
    """Rank inferred structures against all declared targets without docking software."""

    def dock(self, manifest: Manifest, target_pack: dict[str, Any]) -> Manifest:
        structures = manifest.final_state.get("structures", [])
        docking = manifest.final_state.setdefault("docking", [])
        if not isinstance(docking, list):
            docking = []
            manifest.final_state["docking"] = docking
        targets = self._targets(target_pack)
        accepted: list[dict[str, Any]] = []
        rejected = 0
        for structure in structures:
            record = self._record(structure)
            if self._logp(record["smiles"]) > 5 or self._molecular_weight(record["smiles"]) > 600:
                rejected += 1
                continue
            for target in targets:
                accepted.append({
                    "compound_id": record["id"],
                    "target": target,
                    "vina_score": self._vina_score(record["smiles"]),
                })
        accepted.sort(key=lambda result: (result["vina_score"], result["compound_id"], result["target"]))
        for rank, result in enumerate(accepted, start=1):
            result["rank"] = rank
            docking.append(result)
        top_target = accepted[0]["target"] if accepted else "none"
        claim = (
            f"Docked {len(structures) - rejected} candidates against {len(targets)} targets; "
            f"top rank for {top_target} = {accepted[0]['vina_score'] if accepted else 'n/a'} "
            "(docking is ranking, not validation)."
        )
        rationale = Rationale(
            rationale_id=new_rationale_id("target_docking", claim, deterministic=True),
            producer_agent="target_docking",
            claim=claim,
        )
        manifest.rationales.append(rationale)
        for result in docking[-len(accepted):] if accepted else []:
            result["rationale_id"] = rationale.rationale_id
        return manifest

    @staticmethod
    def _targets(target_pack: dict[str, Any]) -> list[str]:
        return [target for pack in target_pack.values() if isinstance(pack, dict) for target in pack]

    @staticmethod
    def _record(structure: Any) -> dict[str, str]:
        if hasattr(structure, "model_dump"):
            structure = structure.model_dump()
        if not isinstance(structure, dict):
            structure = {"structure_id": str(structure), "smiles": ""}
        return {
            "id": str(structure.get("structure_id", structure.get("id", "unknown_structure"))),
            "smiles": str(structure.get("smiles", "")),
        }

    @staticmethod
    def _vina_score(smiles: str) -> float:
        aromatic_bonus = 0.5 if ("aromatic" in smiles.lower() or re.search(r"[cn]", smiles)) else 0.0
        halogen_bonus = 0.3 if ("halogen" in smiles.lower() or re.search(r"Cl|Br|F|I", smiles)) else 0.0
        jitter = (int(hashlib.sha256(smiles.encode()).hexdigest()[:4], 16) % 41 - 20) / 100
        return round(-7.5 + aromatic_bonus + halogen_bonus + jitter, 3)

    @staticmethod
    def _molecular_weight(smiles: str) -> float:
        weights = {"C": 12.01, "N": 14.01, "O": 16.0, "S": 32.06, "P": 30.97, "F": 19.0, "Cl": 35.45, "Br": 79.9, "I": 126.9}
        tokens = re.findall(r"Cl|Br|[CNOSPFI]", smiles)
        return sum(weights[token] for token in tokens)

    @staticmethod
    def _logp(smiles: str) -> float:
        carbons = len(re.findall("C|c", smiles))
        heteroatoms = len(re.findall("N|O|S|P", smiles))
        return max(0.0, carbons * 0.54 - heteroatoms * 0.3)
