"""Metadata-only NCBI SRA RunInfo scraper."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from .cache_manager import CacheManager


class SRAMetadataScraper:
    """Resolve one SRA accession through E-Utilities without downloading reads."""

    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    efetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    def __init__(self, cache_dir: str | Path = ".hyphae_cache", timeout: float = 20.0) -> None:
        self.cache = CacheManager(cache_dir)
        self.timeout = timeout

    def fetch(self, accession: str) -> dict[str, Any]:
        accession = accession.strip().upper()
        if not accession:
            raise ValueError("SRA accession is required")
        if self.cache.has_metadata(accession):
            return self.cache.load_metadata(accession)
        try:
            sra_id = self._search(accession)
            row = self._run_info(sra_id)
        except OSError as exc:
            raise RuntimeError(f"NCBI metadata request failed for {accession}: {exc}") from exc
        metadata = self._normalise(accession, row)
        self.cache.save_metadata(accession, metadata)
        return metadata

    def search_organism(self, organism: str, limit: int = 3) -> list[dict[str, Any]]:
        """Return real RunInfo records for an organism query without downloading reads."""
        term = f'"{organism}"[Organism]'
        query = urlencode({"db": "sra", "term": term, "retmax": max(1, limit), "retmode": "json"})
        try:
            with urlopen(f"{self.esearch_url}?{query}", timeout=self.timeout) as response:
                import json
                ids = json.loads(response.read().decode("utf-8")).get("esearchresult", {}).get("idlist", [])
        except OSError as exc:
            raise RuntimeError(f"NCBI organism search failed for {organism}: {exc}") from exc
        records: list[dict[str, Any]] = []
        for sra_id in ids:
            row = self._run_info(str(sra_id))
            run = (row.get("Run") or "").strip()
            if not run:
                continue
            records.append(self.fetch(run))
        return records

    def _search(self, accession: str) -> str:
        query = urlencode({"db": "sra", "term": accession, "retmax": 1, "retmode": "json"})
        with urlopen(f"{self.esearch_url}?{query}", timeout=self.timeout) as response:
            import json
            payload = json.loads(response.read().decode("utf-8"))
        ids = payload.get("esearchresult", {}).get("idlist", [])
        if not ids:
            raise LookupError(f"SRA accession {accession} was not found by NCBI")
        return str(ids[0])

    def _run_info(self, sra_id: str) -> dict[str, str]:
        query = urlencode({"db": "sra", "id": sra_id, "rettype": "runinfo", "retmode": "text"})
        with urlopen(f"{self.efetch_url}?{query}", timeout=self.timeout) as response:
            text = response.read().decode("utf-8")
        rows = list(csv.DictReader(io.StringIO(text)))
        if not rows:
            raise LookupError(f"NCBI returned no RunInfo record for SRA id {sra_id}")
        return rows[0]

    @staticmethod
    def _normalise(accession: str, row: dict[str, str]) -> dict[str, Any]:
        organism = (row.get("ScientificName") or row.get("Organism") or "").strip()
        read_count = row.get("spots") or row.get("spots_with_mates")
        base_count = row.get("bases")
        if not organism:
            raise ValueError(f"NCBI RunInfo for {accession} has no organism")
        if not read_count:
            raise ValueError(f"NCBI RunInfo for {accession} has no read count")
        try:
            reads, bases = int(read_count), int(base_count or 0)
        except ValueError as exc:
            raise ValueError(f"NCBI RunInfo for {accession} has invalid counts") from exc
        layout = (row.get("LibraryLayout") or "SINGLE").strip().upper()
        paths = [path.strip() for path in (row.get("download_path") or "").split(";") if path.strip()]
        urls = [path.replace("ftp://", "https://", 1) for path in paths]
        return {"accession": accession, "library_type": layout, "read_count": reads, "base_count": bases, "organism": organism, "download_urls_https": urls}


if __name__ == "__main__":
    import sys
    print(SRAMetadataScraper().fetch(sys.argv[1] if len(sys.argv) > 1 else "SRR5832183"))
