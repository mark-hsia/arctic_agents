"""Test fixtures shared across the suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def write_fastq(path: Path, n_reads: int = 50) -> None:
    """Tiny synthetic FASTQ — just enough to exist as an artifact."""
    lines: list[str] = []
    for i in range(n_reads):
        lines += [
            f"@read_{i}",
            "ACGT" * 25,
            "+",
            "I" * 100,
        ]
    path.write_text("\n".join(lines) + "\n")


def write_fake_assembly(path: Path, contigs: int = 5, length: int = 5000) -> None:
    """Synthetic FASTA with deterministic contigs (lengths step down from
    ``length``). Lets ``fasta_assembly_stats`` compute reproducible numbers."""
    out: list[str] = []
    for i in range(contigs):
        out.append(f">contig_{i}")
        L = max(100, length - i * 250)
        out.append("ACGT" * (L // 4))
    path.write_text("\n".join(out) + "\n")


def write_fake_antismash_json(path: Path, regions: list[dict]) -> None:
    """Minimal antiSMASH-shaped JSON with the fields our parser uses."""
    rec_features = [
        {
            "type": "region",
            "location": f"[{r['start']}:{r['end']}](+)",
            "qualifiers": {"product": [r["product"]]},
        }
        for r in regions
    ]
    payload = {
        "records": [
            {
                "id": "contig_0",
                "name": "contig_0",
                "length": 100_000,
                "features": rec_features,
            }
        ]
    }
    path.write_text(json.dumps(payload))


@pytest.fixture
def tiny_paired_fastq(tmp_path: Path) -> tuple[Path, Path]:
    r1 = tmp_path / "x_1.fastq"
    r2 = tmp_path / "x_2.fastq"
    write_fastq(r1)
    write_fastq(r2)
    return r1, r2
