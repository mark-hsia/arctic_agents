"""Append-only metadata cache management for lightweight SRA discovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class CacheManager:
    """Manage validated, accession-keyed SRA metadata without FASTQ payloads."""

    def __init__(self, cache_dir: str | Path = ".hyphae_cache") -> None:
        self.cache_dir = Path(cache_dir)
        self.path = self.cache_dir / "sra_metadata.json"

    def _all(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(f"Corrupt SRA metadata cache: {self.path}") from exc
        if not isinstance(data, dict) or not all(isinstance(key, str) and isinstance(value, dict) for key, value in data.items()):
            raise ValueError(f"Invalid SRA metadata cache: {self.path}")
        return data

    def has_metadata(self, accession: str) -> bool:
        return accession in self._all()

    def load_metadata(self, accession: str) -> dict[str, Any]:
        try:
            return dict(self._all()[accession])
        except KeyError as exc:
            raise KeyError(f"No cached SRA metadata for {accession}") from exc

    def save_metadata(self, accession: str, metadata: dict[str, Any]) -> None:
        """Append a new accession; existing records are immutable."""
        if metadata.get("accession") != accession:
            raise ValueError("Metadata accession does not match its cache key")
        all_metadata = self._all()
        if accession in all_metadata:
            if all_metadata[accession] != metadata:
                raise ValueError(f"Cached metadata for {accession} is immutable and differs from supplied data")
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        all_metadata[accession] = metadata
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(all_metadata, sort_keys=True, indent=2) + "\n")
        temporary.replace(self.path)

    def validate(self) -> None:
        for accession, metadata in self._all().items():
            if metadata.get("accession") != accession or not metadata.get("organism"):
                raise ValueError(f"Invalid metadata entry for {accession}")
            if not isinstance(metadata.get("read_count"), int) or metadata["read_count"] < 0:
                raise ValueError(f"Invalid read_count for {accession}")

    def clean(self) -> int:
        """Remove invalid entries only; valid historical metadata is retained."""
        data = self._all()
        valid = {key: value for key, value in data.items() if value.get("accession") == key and value.get("organism") and isinstance(value.get("read_count"), int)}
        removed = len(data) - len(valid)
        if removed:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(valid, sort_keys=True, indent=2) + "\n")
        return removed


if __name__ == "__main__":
    print("SRA metadata cache is ready")
