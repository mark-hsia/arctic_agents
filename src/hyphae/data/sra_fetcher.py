"""Cached, real SRA FASTQ acquisition."""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
from pathlib import Path
from typing import TypeAlias
from urllib.parse import urlencode
from urllib.request import urlopen

FastqPaths: TypeAlias = tuple[str, str] | str


class SraFetcher:
    """Fetch FASTQ files from NCBI SRA via toolkit or public metadata APIs."""

    def __init__(self, cache_dir: str = ".hyphae_cache/fastq") -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        self.efetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    def fetch(self, sra_accession: str, paired: bool = True) -> FastqPaths:
        """Fetch cached or real FASTQ files, raising with remediation on failure."""
        cached_r1 = self.cache_dir / f"{sra_accession}_1.fastq"
        cached_r2 = self.cache_dir / f"{sra_accession}_2.fastq"
        if cached_r1.is_file() and (not paired or cached_r2.is_file()):
            return (str(cached_r1), str(cached_r2)) if paired else str(cached_r1)
        try:
            if self._has_fastq_dump():
                return self._fetch_with_sra_toolkit(sra_accession, paired)
            if self._has_fasterq_dump():
                return self._fetch_with_fasterq_dump(sra_accession, paired)
            return self._fetch_from_ftp(sra_accession, paired)
        except Exception as exc:
            raise RuntimeError(
                f"Could not fetch {sra_accession}. Install SRA Toolkit (`conda install -c bioconda sra-tools`) "
                "or verify NCBI/ENA network access."
            ) from exc

    @staticmethod
    def _available(binary: str) -> bool:
        try:
            result = subprocess.run(
                [binary, "--version"], capture_output=True, text=True, timeout=5, check=False
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _has_fastq_dump(self) -> bool:
        return self._available("fastq-dump")

    def _has_fasterq_dump(self) -> bool:
        return self._available("fasterq-dump")

    def _fetch_with_sra_toolkit(self, accession: str, paired: bool) -> FastqPaths:
        cmd = ["fastq-dump", "--outdir", str(self.cache_dir)]
        if paired:
            cmd.append("--split-files")
        cmd.append(accession)
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        return self._result_paths(accession, paired)

    def _fetch_with_fasterq_dump(self, accession: str, paired: bool) -> FastqPaths:
        cmd = ["fasterq-dump", "--outdir", str(self.cache_dir)]
        if paired:
            cmd.append("--split-files")
        cmd.append(accession)
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        return self._result_paths(accession, paired)

    def _result_paths(self, accession: str, paired: bool) -> FastqPaths:
        r1 = self.cache_dir / f"{accession}_1.fastq"
        r2 = self.cache_dir / f"{accession}_2.fastq"
        single = self.cache_dir / f"{accession}.fastq"
        if paired and r1.is_file() and r2.is_file():
            return str(r1), str(r2)
        if not paired and (single.is_file() or r1.is_file()):
            return str(single if single.is_file() else r1)
        raise RuntimeError(f"SRA toolkit did not create expected FASTQ files for {accession}")

    def _fetch_from_ftp(self, accession: str, paired: bool) -> FastqPaths:
        """Resolve accession with E-utilities, then download the EBI FASTQ path."""
        params = urlencode({"db": "sra", "term": accession, "retmax": 1, "retmode": "json"})
        with urlopen(f"{self.esearch_url}?{params}", timeout=10) as response:
            search = json.loads(response.read().decode())
        ids = search.get("esearchresult", {}).get("idlist", [])
        if not ids:
            raise ValueError(f"SRA accession {accession} not found")
        fetch_params = urlencode({"db": "sra", "id": ids[0], "rettype": "runinfo", "retmode": "json"})
        # Validate that the run remains resolvable even though the file layout
        # is derived from the accession and hosted by ENA.
        with urlopen(f"{self.efetch_url}?{fetch_params}", timeout=10) as response:
            response.read()
        return self._download_from_ftp(self._build_ftp_path(accession), accession, paired)

    @staticmethod
    def _build_ftp_path(accession: str) -> str:
        """Build the common ENA FASTQ directory URL for an SRR/ERR/DRR run."""
        return f"ftp://ftp.sra.ebi.ac.uk/vol1/fastq/{accession[:6]}/{accession}/"

    def _download_from_ftp(self, ftp_path: str, accession: str, paired: bool) -> FastqPaths:
        paths = [(f"{accession}_1.fastq.gz", self.cache_dir / f"{accession}_1.fastq")]
        if paired:
            paths.append((f"{accession}_2.fastq.gz", self.cache_dir / f"{accession}_2.fastq"))
        for remote_name, destination in paths:
            compressed = destination.with_suffix(destination.suffix + ".gz")
            subprocess.run(
                ["curl", "-fLsS", ftp_path + remote_name, "-o", str(compressed)],
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
            with gzip.open(compressed, "rb") as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)
            compressed.unlink(missing_ok=True)
        return self._result_paths(accession, paired)
