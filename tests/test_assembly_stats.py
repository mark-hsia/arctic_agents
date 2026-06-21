from pathlib import Path

from hyphae.tools.assemblers import fasta_assembly_stats


def test_fasta_assembly_stats_reproducible(tmp_path: Path) -> None:
    f = tmp_path / "a.fasta"
    f.write_text(">a\n" + "ACGT" * 250 + "\n>b\n" + "ACGT" * 100 + "\n>c\n" + "ACGT" * 50 + "\n")
    s = fasta_assembly_stats(f)
    assert s["n_contigs"] == 3
    assert s["total_length"] == 1000 + 400 + 200
    assert s["largest_contig"] == 1000
    # n50: cumulative half = 800 -> first contig (1000) covers it
    assert s["n50"] == 1000


def test_fasta_assembly_stats_empty_fasta(tmp_path: Path) -> None:
    f = tmp_path / "empty.fasta"
    f.write_text("")
    s = fasta_assembly_stats(f)
    assert s == {"n_contigs": 0, "total_length": 0, "n50": 0, "largest_contig": 0}
