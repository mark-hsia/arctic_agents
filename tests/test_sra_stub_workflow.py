from __future__ import annotations

from pathlib import Path

from hyphae.tools.fastq_stub_generator import FASTQStubGenerator
from hyphae.tools.sra_metadata_scraper import SRAMetadataScraper


def test_metadata_scraper_caches_normalised_ncbi_runinfo(tmp_path: Path, monkeypatch) -> None:
    scraper = SRAMetadataScraper(tmp_path)
    monkeypatch.setattr(scraper, "_search", lambda accession: "123")
    monkeypatch.setattr(scraper, "_run_info", lambda _: {
        "ScientificName": "Cladonia rangiferina", "spots": "1000", "bases": "24000",
        "LibraryLayout": "PAIRED", "download_path": "ftp://example.invalid/SRR5832183",
    })
    metadata = scraper.fetch("SRR5832183")
    assert metadata["organism"] == "Cladonia rangiferina"
    assert metadata["read_count"] == 1000
    assert metadata["download_urls_https"] == ["https://example.invalid/SRR5832183"]
    assert scraper.fetch("SRR5832183") == metadata


def test_stub_fastq_is_valid_bounded_and_deterministic(tmp_path: Path) -> None:
    first = FASTQStubGenerator(seed=42).generate_paired("SRR5832183", 1_000, tmp_path / "one")
    second = FASTQStubGenerator(seed=42).generate_paired("SRR5832183", 1_000, tmp_path / "two")
    for first_path, second_path in zip(first, second):
        one, two = Path(first_path), Path(second_path)
        assert one.read_bytes() == two.read_bytes()
        assert one.stat().st_size <= 10_240
        lines = one.read_text().splitlines()
        assert len(lines) % 4 == 0
        assert lines[0].startswith("@SRR5832183_")
        assert "[STUB_ACCESSION=SRR5832183]" in lines[0]
        assert all(len(lines[index + 1]) == len(lines[index + 3]) for index in range(0, len(lines), 4))
