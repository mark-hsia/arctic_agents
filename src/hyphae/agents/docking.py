"""Deterministic ranking-only docking heuristic."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..ids import new_rationale_id
from ..state import Rationale

if TYPE_CHECKING:
    from ..runtime.deterministic_executor import Manifest


class TargetDockingAgent:
    """Rank inferred structures against all declared targets without docking software."""

    def dock(
        self,
        manifest: Manifest,
        target_pack: dict[str, Any],
        use_vina: bool = False,
        vina_bin: str = "vina",
    ) -> Manifest:
        """Dock structures with Vina only; no heuristic ranking is emitted."""
        if not use_vina:
            raise RuntimeError(
                "Real docking requires use_vina=True. Install AutoDock Vina and provide receptor_path "
                "for every target; heuristic docking is disabled."
            )
        structures = manifest.final_state.get("structures", [])
        docking = manifest.final_state.setdefault("docking", [])
        if not isinstance(docking, list):
            docking = []
            manifest.final_state["docking"] = docking
        targets = self._flatten_target_pack(target_pack)
        accepted: list[dict[str, Any]] = []
        rejected = 0
        for structure in structures:
            record = self._record(structure)
            if self._logp(record["smiles"]) > 5 or self._molecular_weight(record["smiles"]) > 600:
                rejected += 1
                continue
            for target, target_data in targets.items():
                score, source = self._score_structure(record["smiles"], target_data, vina_bin)
                accepted.append({
                    "compound_id": record["id"],
                    "target": target,
                    "vina_score": score,
                    "source": source,
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
    def _flatten_target_pack(target_pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Flatten ``{pathogen: {target: metadata}}`` target packs."""
        return {
            f"{pathogen}/{target}": data if isinstance(data, dict) else {}
            for pathogen, targets in target_pack.items()
            if isinstance(targets, dict)
            for target, data in targets.items()
        }

    def _score_structure(
        self, smiles: str, target_data: dict[str, Any], vina_bin: str
    ) -> tuple[float, str]:
        receptor = Path(str(target_data.get("receptor_path", "")))
        if not receptor.is_file():
            raise FileNotFoundError("Target receptor_path is required and must reference a Vina-ready receptor file")
        ligand_path = self._smiles_to_pdb(smiles)
        if ligand_path is None:
            raise RuntimeError("RDKit could not convert SMILES; install RDKit and provide a valid structure")
        try:
            result = subprocess.run(
                [vina_bin, "--ligand", str(ligand_path), "--receptor", str(receptor), "--exhaustiveness", "8"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            score = self._parse_vina_affinity(result.stdout) if result.returncode == 0 else None
            if score is None:
                raise RuntimeError(f"Vina failed to return an affinity: {result.stderr[-500:]}")
            return score, "vina"
        except Exception as exc:
            raise RuntimeError(f"Vina docking failed: {exc}") from exc
        finally:
            ligand_path.unlink(missing_ok=True)

    @staticmethod
    def _smiles_to_pdb(smiles: str) -> Path | None:
        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem

            molecule = Chem.MolFromSmiles(smiles)
            if molecule is None:
                return None
            molecule = Chem.AddHs(molecule)
            AllChem.EmbedMolecule(molecule, randomSeed=42)
            with tempfile.NamedTemporaryFile(suffix=".pdb", delete=False) as handle:
                path = Path(handle.name)
            Chem.MolToPDBFile(molecule, str(path))
            return path
        except Exception:
            return None

    @staticmethod
    def _parse_vina_affinity(stdout: str) -> float | None:
        match = re.search(r"(?:Affinity:|^\s*1\s+)(-?\d+(?:\.\d+)?)", stdout, re.MULTILINE)
        return float(match.group(1)) if match else None

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
    def _molecular_weight(smiles: str) -> float:
        weights = {"C": 12.01, "N": 14.01, "O": 16.0, "S": 32.06, "P": 30.97, "F": 19.0, "Cl": 35.45, "Br": 79.9, "I": 126.9}
        tokens = re.findall(r"Cl|Br|[CNOSPFI]", smiles)
        return sum(weights[token] for token in tokens)

    @staticmethod
    def _logp(smiles: str) -> float:
        carbons = len(re.findall("C|c", smiles))
        heteroatoms = len(re.findall("N|O|S|P", smiles))
        return max(0.0, carbons * 0.54 - heteroatoms * 0.3)
