"""Deterministic BGC summary and rarity-based novelty signal."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..runtime.deterministic_executor import Manifest


@dataclass(frozen=True)
class BgcAnalysisResult:
    total_bgc_count: int
    bgc_types: dict[str, int]
    most_novel_bgc_id: str
    evidence: str


class BgcAnalyzer:
    """Flag a representative BGC from the least frequent discovered type."""

    def analyze(self, manifest: Manifest) -> BgcAnalysisResult:
        bgcs = manifest.final_state.get("bgcs", [])
        normalized = [self._record(item) for item in bgcs]
        counts = Counter(record["type"] for record in normalized)
        if not normalized:
            return BgcAnalysisResult(0, {}, "", "Found 0 BGCs; no novelty signal is available.")
        rare_type = min(counts, key=lambda bgc_type: (counts[bgc_type], bgc_type))
        novel = next(record for record in normalized if record["type"] == rare_type)
        return BgcAnalysisResult(
            total_bgc_count=len(normalized),
            bgc_types=dict(sorted(counts.items())),
            most_novel_bgc_id=novel["id"],
            evidence=(
                f"Found {len(normalized)} BGCs; most unusual type is {rare_type} "
                f"({counts[rare_type]} occurrences)."
            ),
        )

    @staticmethod
    def _record(item: Any) -> dict[str, str]:
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        if not isinstance(item, dict):
            return {"id": str(item), "type": "other"}
        return {
            "id": str(item.get("bgc_id", item.get("id", "unknown_bgc"))),
            "type": str(item.get("bgc_class", item.get("type", item.get("product", "other")))).lower(),
        }
