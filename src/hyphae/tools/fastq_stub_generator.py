"""Small, deterministic and explicitly marked FASTQ fixtures."""

from __future__ import annotations

import hashlib
from pathlib import Path


class FASTQStubGenerator:
    """Generate development fixtures; these are not biological observations."""

    def __init__(self, seed: int = 42, max_bytes: int = 10_240) -> None:
        self.seed, self.max_bytes = seed, max_bytes

    def generate_paired(self, accession: str, num_reads: int, output_dir: str | Path) -> list[str]:
        return self._generate(accession, num_reads, output_dir, paired=True)

    def generate_single(self, accession: str, num_reads: int, output_dir: str | Path) -> list[str]:
        return self._generate(accession, num_reads, output_dir, paired=False)

    def _generate(self, accession: str, num_reads: int, output_dir: str | Path, *, paired: bool) -> list[str]:
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        paths = [destination / f"{accession}_{mate}.fastq" for mate in (1, 2)] if paired else [destination / f"{accession}.fastq"]
        for mate, path in enumerate(paths, start=1):
            self._write(path, accession, mate, num_reads)
        return [str(path) for path in paths]

    def _write(self, path: Path, accession: str, mate: int, requested: int) -> None:
        sequence_length = 24
        with path.open("w") as handle:
            for index in range(max(0, requested)):
                sequence = self._sequence(accession, mate, index, sequence_length)
                record = f"@{accession}_{mate}_STUB_{index} [STUB_ACCESSION={accession}]\n{sequence}\n+\n{'I' * sequence_length}\n"
                if handle.tell() + len(record.encode()) > self.max_bytes:
                    break
                handle.write(record)

    def _sequence(self, accession: str, mate: int, index: int, length: int) -> str:
        digest = hashlib.sha256(f"{self.seed}:{accession}:{mate}:{index}".encode()).digest()
        alphabet = "ACGT"
        return "".join(alphabet[byte % 4] for byte in (digest * ((length // len(digest)) + 1))[:length])


if __name__ == "__main__":
    print(FASTQStubGenerator().generate_paired("STUB", 100, "."))
