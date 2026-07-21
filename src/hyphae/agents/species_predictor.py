"""Fast, deterministic species and genome-novelty heuristics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median
from typing import TYPE_CHECKING, Any

from ..knowledge import KnowledgeBase
if TYPE_CHECKING:
    from ..runtime.deterministic_executor import Manifest


class GenomeComparator:
    """Calculate assembly statistics that serve as a lightweight genome fingerprint."""

    def compare(self, fasta: Path | str) -> dict[str, Any]:
        lengths: list[int] = []
        gc_bases = 0
        total_bp = 0
        current_length = 0
        with Path(fasta).open() as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith(">"):
                    if current_length:
                        lengths.append(current_length)
                    current_length = 0
                    continue
                sequence = line.upper()
                current_length += len(sequence)
                total_bp += len(sequence)
                gc_bases += sequence.count("G") + sequence.count("C")
        if current_length:
            lengths.append(current_length)

        ordered = sorted(lengths, reverse=True)
        running = 0
        n50 = 0
        for length in ordered:
            running += length
            if running >= total_bp / 2:
                n50 = length
                break
        distribution = {
            "min": min(lengths) if lengths else 0,
            "max": max(lengths) if lengths else 0,
            "mean": mean(lengths) if lengths else 0.0,
            "median": median(lengths) if lengths else 0.0,
        }
        return {
            "n_contigs": len(lengths),
            "total_bp": total_bp,
            "n50": n50,
            "gc_content": gc_bases / total_bp if total_bp else 0.0,
            "contig_length_distribution": distribution,
        }


class NoveltyScorer:
    """Score novelty from a taxonomic assignment and unusual assembly statistics."""

    def __init__(self, knowledge_base: KnowledgeBase | None = None) -> None:
        self.kb = knowledge_base or KnowledgeBase()

    def score(
        self,
        assembly_stats: dict[str, Any],
        taxonomy_result: str | Any,
        target_species: str | None = None,
    ) -> dict[str, Any]:
        if target_species is None and isinstance(assembly_stats, dict) and (
            "domains" in assembly_stats or "type" in assembly_stats
        ):
            return self._score_bgc(assembly_stats, taxonomy_result)
        taxonomy_text = self._taxonomy_text(taxonomy_result)
        assigned_taxid = self._assigned_taxid(taxonomy_text)
        if assigned_taxid == "unclassified":
            return {
                "novelty_score": 0.9,
                "rationale_text": "Taxonomy assignment is unclassified; treating the sample as highly novel.",
            }
        target_species = target_species or "unknown"
        normalized_target = target_species.replace("_", " ").lower()
        if (
            normalized_target in taxonomy_text.lower()
            or target_species.lower() in taxonomy_text.lower()
            or assigned_taxid == target_species
        ):
            return {
                "novelty_score": 0.1,
                "rationale_text": f"Taxonomy matches target species {target_species}.",
            }

        bonus = 0.0
        signals: list[str] = []
        n50 = float(assembly_stats.get("n50", 0))
        gc_content = float(assembly_stats.get("gc_content", 0))
        n_contigs = int(assembly_stats.get("n_contigs", 0))
        if n50 < 5_000 or gc_content < 0.35 or gc_content > 0.60:
            bonus += 0.3
            signals.append("unusual N50 or GC content")
        if n_contigs > 500:
            bonus += 0.2
            signals.append("high contig count")
        novelty = min(0.9, 0.1 + bonus)
        explanation = ", ".join(signals) if signals else "no unusual assembly signals"
        return {
            "novelty_score": novelty,
            "rationale_text": f"Taxonomy differs from {target_species}; {explanation}.",
        }

    def _score_bgc(self, bgc: dict[str, Any], taxonomy: Any) -> dict[str, Any]:
        """Score a BGC against cached MIBiG product classes."""
        taxonomy_text = self._taxonomy_text(taxonomy)
        base_novelty = float(bgc.get("novelty_score", 0.5))
        if "unclassified" in taxonomy_text.lower():
            base_novelty = max(base_novelty, 0.7)
        similar = self.kb.find_similar_bgc(
            list(bgc.get("domains", [])), str(bgc.get("type", "unknown"))
        )
        if similar:
            base_novelty *= 0.7
            suffix = f"; similar to MIBiG BGCs: {[match[0] for match in similar[:2]]}"
        else:
            suffix = "; not found in MIBiG"
        base_novelty = round(max(0.0, min(1.0, base_novelty)), 6)
        return {"score": base_novelty, "rationale": f"Novelty={base_novelty:.2f}{suffix}"}

    @staticmethod
    def _taxonomy_text(taxonomy_result: str | Any) -> str:
        if isinstance(taxonomy_result, str):
            return taxonomy_result
        if isinstance(taxonomy_result, dict):
            return " ".join(str(value) for value in taxonomy_result.values() if value is not None)
        if hasattr(taxonomy_result, "model_dump"):
            return NoveltyScorer._taxonomy_text(taxonomy_result.model_dump())
        return str(taxonomy_result or "unclassified")

    @staticmethod
    def _assigned_taxid(taxonomy_text: str) -> str:
        fields = taxonomy_text.split("\t")
        if not taxonomy_text or taxonomy_text.lower().startswith("u\t") or "unclassified" in taxonomy_text.lower():
            return "unclassified"
        return fields[2] if len(fields) >= 3 else taxonomy_text.strip()


@dataclass(frozen=True)
class SpeciesPrediction:
    sample_id: str
    predicted_species: str
    novelty_score: float
    confidence: float
    evidence: str


class SpeciesPredictorAgent:
    """Predict one species label and novelty estimate for each manifest sample."""

    def __init__(self, comparator: GenomeComparator | None = None, scorer: NoveltyScorer | None = None) -> None:
        self.comparator = comparator or GenomeComparator()
        self.scorer = scorer or NoveltyScorer()

    def predict(self, manifest: Manifest, target_species: str) -> list[SpeciesPrediction]:
        final_state = manifest.final_state
        taxonomy = final_state.get("taxonomy", {})
        predictions: list[SpeciesPrediction] = []
        for sample in final_state.get("samples", []):
            sample_id = self._sample_id(sample)
            assembly_path = self._assembly_path(manifest, sample_id)
            if assembly_path is None or not assembly_path.is_file():
                continue
            stats = self.comparator.compare(assembly_path)
            tax_result = taxonomy.get(sample_id, "unclassified") if isinstance(taxonomy, dict) else "unclassified"
            novelty = self.scorer.score(stats, tax_result, target_species)
            novelty_score = float(novelty["novelty_score"])
            taxonomy_text = self.scorer._taxonomy_text(tax_result)
            predicted = self._predicted_species(taxonomy_text, sample_id, novelty_score)
            predictions.append(SpeciesPrediction(
                sample_id=sample_id,
                predicted_species=predicted,
                novelty_score=novelty_score,
                confidence=(1.0 - novelty_score) * 0.95,
                evidence=f"{novelty['rationale_text']} N50={stats['n50']}; GC={stats['gc_content']:.1%}.",
            ))
        return predictions

    @staticmethod
    def _sample_id(sample: Any) -> str:
        if isinstance(sample, str):
            return Path(sample).stem
        if isinstance(sample, dict):
            return str(sample.get("sample_id", sample.get("id", "unknown")))
        return str(getattr(sample, "sample_id", "unknown"))

    @staticmethod
    def _predicted_species(taxonomy_text: str, sample_id: str, novelty_score: float) -> str:
        if novelty_score > 0.6 or "unclassified" in taxonomy_text.lower():
            genus = "Unknown"
            fields = taxonomy_text.split("\t")
            if len(fields) > 3 and fields[3].isalpha():
                genus = fields[3]
            return f"Unknown_{genus}_{sample_id}"
        fields = taxonomy_text.split("\t")
        return fields[-1].strip() if len(fields) > 3 and fields[-1].strip() else taxonomy_text.strip()

    @staticmethod
    def _assembly_path(manifest: Manifest, sample_id: str) -> Path | None:
        assemblies = manifest.final_state.get("assemblies", {})
        ref = assemblies.get(sample_id) if isinstance(assemblies, dict) else None
        if hasattr(ref, "assembly_artifact_id"):
            ref = ref.assembly_artifact_id
        if isinstance(ref, dict):
            ref = ref.get("assembly_artifact_id") or ref.get("path")
        artifacts = {artifact.artifact_id: artifact for artifact in manifest.artifacts}
        if ref in artifacts:
            ref = artifacts[ref].path
        if ref:
            return Path(str(ref))
        # Typed manifests can identify an assembly artifact through metadata.
        for artifact in manifest.artifacts:
            if artifact.metadata.get("sample_id") == sample_id and artifact.producer_agent == "assembly":
                return Path(artifact.path)
        return None


def analyze_manifest(manifest: Manifest, target_species: str) -> dict[str, Any]:
    """Run full species and BGC novelty analysis on a manifest."""
    from .bgc_analyzer import BgcAnalyzer

    predictions = SpeciesPredictorAgent().predict(manifest, target_species)
    bgc_analysis = BgcAnalyzer().analyze(manifest)
    return {
        "species_predictions": [asdict(prediction) for prediction in predictions],
        "bgc_analysis": asdict(bgc_analysis),
        "summary": (
            f"Analyzed {len(predictions)} samples; "
            f"{sum(prediction.novelty_score > 0.6 for prediction in predictions)} flagged as novel"
        ),
    }
