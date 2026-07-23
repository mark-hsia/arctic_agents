"""Best-effort local reference caches for MIBiG and ChEMBL metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class KnowledgeBase:
    """Local cache for MIBiG, ChEMBL, and other reference data."""

    def __init__(self, cache_dir: str = ".hyphae_cache") -> None:
        self.cache_dir = Path(cache_dir)
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            # A read-only working directory must not prevent heuristic runs.
            pass
        self.mibig_index = self._load_or_fetch_mibig()
        self.chembl_subset = self._load_or_fetch_chembl()

    def _load_or_fetch_mibig(self) -> dict[str, dict[str, Any]]:
        """Load only an existing local MIBiG cache; absence is unknown."""
        cache_file = self.cache_dir / "mibig_index.json"
        cached = self._load_json(cache_file)
        if cached is not None:
            return cached
        return {}

    def _load_or_fetch_chembl(self) -> dict[str, dict[str, Any]]:
        """Load a local antifungal ChEMBL subset; an empty index is valid."""
        cache_file = self.cache_dir / "chembl_subset.json"
        cached = self._load_json(cache_file)
        if cached is not None:
            return cached
        return {}

    @staticmethod
    def _load_json(path: Path) -> dict[str, dict[str, Any]] | None:
        try:
            data = json.loads(path.read_text())
            return data if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        try:
            path.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    def lookup_bgc(self, bgc_id: str) -> dict[str, Any] | None:
        return self.mibig_index.get(bgc_id)

    def lookup_smiles(self, smiles: str) -> dict[str, Any] | None:
        return self.chembl_subset.get(smiles)

    def find_similar_bgc(self, domains: list[Any], product_class: str) -> list[tuple[str, dict[str, Any]]]:
        """Return up to five same-product-class MIBiG references.

        Domain overlap breaks ties when MIBiG domain annotations are present.
        """
        requested = {str(domain).lower() for domain in domains}
        matches = [
            (bgc_id, data)
            for bgc_id, data in self.mibig_index.items()
            if str(product_class).lower() in {str(item).lower() for item in data.get("product", [])}
        ]
        matches.sort(
            key=lambda item: len(requested & {str(domain).lower() for domain in item[1].get("domains", [])}),
            reverse=True,
        )
        return matches[:5]
