"""Human-readable and machine-readable reporting for a completed manifest."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..runtime.deterministic_executor import Manifest


class ReporterAgent:
    """Render ranked candidates, BGC dossiers, and a portable run card."""

    def generate_report(self, manifest: Manifest, output_dir: Path) -> None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        candidates = self._rank_candidates(manifest)
        self._write_summary(output_dir, candidates)
        self._write_dossiers(manifest, output_dir)
        self._write_whitepaper(manifest, output_dir, candidates)
        self._write_run_card(manifest, output_dir, candidates)

    def _rank_candidates(self, manifest: Manifest) -> list[dict[str, Any]]:
        structures = {self._get(record, "structure_id", "id"): self._as_dict(record)
                      for record in manifest.final_state.get("structures", [])}
        bgcs = {self._get(record, "bgc_id", "id"): self._as_dict(record)
                for record in manifest.final_state.get("bgcs", [])}
        novelty = manifest.final_state.get("novelty", {})
        candidates: list[dict[str, Any]] = []
        for docking_entry in manifest.final_state.get("docking", []):
            docking = self._as_dict(docking_entry)
            structure = structures.get(str(docking.get("compound_id", docking.get("structure_id", ""))))
            if structure is None:
                continue
            bgc = bgcs.get(str(structure.get("bgc_id", "")))
            if bgc is None:
                continue
            bgc_id = str(bgc.get("bgc_id", bgc.get("id", "")))
            score = novelty.get(bgc_id, 0.5) if isinstance(novelty, dict) else 0.5
            if isinstance(score, dict):
                score = score.get("score", 0.5)
            rank_score = (
                float(docking.get("vina_score", 0.0)) * 0.4
                + float(structure.get("confidence", 0.0)) * 0.3
                + float(score) * 0.3
            )
            candidates.append({
                "rank_score": rank_score,
                "structure": structure,
                "bgc": bgc,
                "docking": docking,
                "novelty": float(score),
            })
        return sorted(candidates, key=lambda candidate: candidate["rank_score"], reverse=True)

    def _write_summary(self, output_dir: Path, candidates: list[dict[str, Any]]) -> None:
        lines = ["# Antifungal Candidates - Summary", ""]
        for index, candidate in enumerate(candidates[:10], start=1):
            structure, bgc, docking = candidate["structure"], candidate["bgc"], candidate["docking"]
            lines.extend([
                f"## Rank {index}: {structure.get('smiles', '')}",
                f"- Source BGC: {bgc.get('bgc_id', bgc.get('id', 'unknown'))}",
                f"- Novelty: {candidate['novelty']:.2f}",
                f"- Top target: {docking.get('target', 'unknown')} (score={float(docking.get('vina_score', 0)):.1f})",
                f"- Confidence: {float(structure.get('confidence', 0)):.2f}",
                "",
            ])
        if not candidates:
            lines.extend(["No docked candidates were available for ranking.", ""])
        (output_dir / "summary.md").write_text("\n".join(lines))

    def _write_dossiers(self, manifest: Manifest, output_dir: Path) -> None:
        dossier_dir = output_dir / "per_bgc"
        dossier_dir.mkdir(exist_ok=True)
        structures = [self._as_dict(record) for record in manifest.final_state.get("structures", [])]
        for raw_bgc in manifest.final_state.get("bgcs", []):
            bgc = self._as_dict(raw_bgc)
            bgc_id = str(bgc.get("bgc_id", bgc.get("id", "unknown_bgc")))
            domains = ", ".join(str(domain) for domain in bgc.get("domains", []))
            lines = [
                f"# BGC: {bgc_id}",
                f"Type: {bgc.get('tool', bgc.get('type', bgc.get('bgc_class', 'unknown')))}",
                f"Domains: {domains}",
                f"Source MAG: {bgc.get('source_mag', bgc.get('mag_id', 'unknown'))}",
                f"Confidence: {float(bgc.get('confidence', 0)):.2f}",
                f"GCF candidate: {bgc.get('gcf_candidate', 'unknown')}",
                "",
            ]
            for structure in structures:
                if structure.get("bgc_id") != bgc_id:
                    continue
                lines.extend([
                    f"### Structure {structure.get('structure_id', 'unknown')}",
                    f"SMILES: {structure.get('smiles', '')}",
                    f"Confidence: {float(structure.get('confidence', 0)):.2f}",
                    "",
                ])
            filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", bgc_id)
            (dossier_dir / f"{filename}.md").write_text("\n".join(lines))

    def _write_whitepaper(self, manifest: Manifest, output_dir: Path, candidates: list[dict[str, Any]]) -> None:
        final = manifest.final_state
        accepted = [self._as_dict(rationale) for rationale in manifest.rationales if rationale.accepted]
        budget = self._budget(manifest)
        top_smiles = candidates[0]["structure"].get("smiles", "") if candidates else "None"
        whitepaper = f"""# Antifungal Natural Product Discovery Run

## Summary
Analyzed {len(final.get('samples', []))} samples, assembled {len(final.get('assemblies', {}))} MAGs, found {len(final.get('bgcs', []))} BGCs.

## Top Candidates
{top_smiles}

## Methodology
All docking results are for ranking purposes only, not validation. Structures were inferred from BGC domain logic.

## Rationales
{json.dumps(accepted, indent=2, default=str)}

## Budget Summary
Total tokens: {budget['tokens']}
Total dollars: {budget['dollars']:.2f}
Wall-clock: {budget['wall_clock_seconds']:.1f}s
"""
        (output_dir / "whitepaper.md").write_text(whitepaper)

    def _write_run_card(self, manifest: Manifest, output_dir: Path, candidates: list[dict[str, Any]]) -> None:
        bgcs = [self._as_dict(record) for record in manifest.final_state.get("bgcs", [])]
        budget = self._budget(manifest)
        run_card = {
            "run_id": manifest.run_id,
            "intent": self._jsonable(getattr(manifest, "intent", None)),
            "candidate_count": len(candidates),
            "top_candidates": [
                {
                    "rank": index,
                    "smiles": candidate["structure"].get("smiles", ""),
                    "novelty": candidate["novelty"],
                    "top_target": candidate["docking"].get("target"),
                    "vina_score": candidate["docking"].get("vina_score"),
                }
                for index, candidate in enumerate(candidates[:10], start=1)
            ],
            "bgc_summary": {
                "total": len(bgcs),
                "by_type": dict(sorted(Counter(
                    str(bgc.get("tool", bgc.get("type", bgc.get("bgc_class", "unknown")))) for bgc in bgcs
                ).items())),
                "novel_count": sum("orphan" in str(bgc.get("gcf_candidate", "")).lower() for bgc in bgcs),
            },
            "budget": budget,
        }
        (output_dir / "run_card.json").write_text(json.dumps(run_card, indent=2, default=str) + "\n")

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _get(value: Any, *keys: str) -> Any:
        record = ReporterAgent._as_dict(value)
        return next((record[key] for key in keys if key in record), "")

    @staticmethod
    def _jsonable(value: Any) -> Any:
        return value.model_dump() if hasattr(value, "model_dump") else value

    @staticmethod
    def _budget(manifest: Manifest) -> dict[str, float | int]:
        entries = manifest.budget_entries
        return {
            "tokens": sum(entry.tokens for entry in entries),
            "dollars": sum(entry.dollars for entry in entries),
            "wall_clock_seconds": sum(entry.wall_clock_seconds for entry in entries),
        }


def generate_report(manifest: Manifest, output_dir: Path = Path("report")) -> None:
    """Generate the report directory for a completed manifest."""
    ReporterAgent().generate_report(manifest, output_dir)
