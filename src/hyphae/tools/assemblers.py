"""Assembly tool wrappers (metaSPAdes, MEGAHIT) plus shared assembly metrics."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .base import Tool, ToolRunResult, ToolUnavailable, run_shell


def fasta_assembly_stats(fasta_path: Path) -> dict[str, int]:
    """Compute N50, total length, n_contigs, largest_contig from a FASTA file.

    Pure-Python so it works without any bio tool installed."""

    lengths: list[int] = []
    cur = 0
    with fasta_path.open() as fh:
        for line in fh:
            if line.startswith(">"):
                if cur > 0:
                    lengths.append(cur)
                cur = 0
            else:
                cur += len(line.strip())
    if cur > 0:
        lengths.append(cur)
    if not lengths:
        return {"n_contigs": 0, "total_length": 0, "n50": 0, "largest_contig": 0}
    lengths.sort(reverse=True)
    total = sum(lengths)
    half = total / 2
    running = 0
    n50 = 0
    for L in lengths:
        running += L
        if running >= half:
            n50 = L
            break
    return {
        "n_contigs": len(lengths),
        "total_length": total,
        "n50": n50,
        "largest_contig": lengths[0],
    }


class MetaSpades(Tool):
    tool_id = "assembly.metaspades"
    binary = "metaspades.py"

    def run(self, **kwargs: Any) -> ToolRunResult:
        in1: Path = Path(kwargs["in1"])
        in2: Path | None = Path(kwargs["in2"]) if kwargs.get("in2") else None
        outdir: Path = Path(kwargs["outdir"])
        threads: int = int(kwargs.get("threads", 4))
        outdir.mkdir(parents=True, exist_ok=True)
        if not self.is_available():
            raise ToolUnavailable("metaspades.py not on PATH")
        cmd = [self.binary, "-1", str(in1)]  # type: ignore[list-item]
        if in2:
            cmd += ["-2", str(in2)]
        cmd += ["-o", str(outdir), "-t", str(threads), "--only-assembler"]
        t0 = time.time()
        run_shell(cmd)
        contigs = outdir / "contigs.fasta"
        if not contigs.is_file():
            raise RuntimeError("metaSPAdes finished without producing contigs.fasta")
        metrics = fasta_assembly_stats(contigs)
        return ToolRunResult(
            tool_id=self.tool_id,
            output_paths=[contigs],
            metrics=metrics,
            duration_seconds=time.time() - t0,
        )


class Megahit(Tool):
    tool_id = "assembly.megahit"
    binary = "megahit"

    def run(self, **kwargs: Any) -> ToolRunResult:
        in1: Path = Path(kwargs["in1"])
        in2: Path | None = Path(kwargs["in2"]) if kwargs.get("in2") else None
        outdir: Path = Path(kwargs["outdir"])
        threads: int = int(kwargs.get("threads", 4))
        if not self.is_available():
            raise ToolUnavailable("megahit not on PATH")
        # MEGAHIT requires the output directory not to exist.
        if outdir.exists():
            raise RuntimeError(f"MEGAHIT output dir {outdir} must not exist")
        cmd = [self.binary, "-1", str(in1)]  # type: ignore[list-item]
        if in2:
            cmd += ["-2", str(in2)]
        cmd += ["-o", str(outdir), "-t", str(threads)]
        t0 = time.time()
        run_shell(cmd)
        contigs = outdir / "final.contigs.fa"
        if not contigs.is_file():
            raise RuntimeError("MEGAHIT finished without final.contigs.fa")
        metrics = fasta_assembly_stats(contigs)
        return ToolRunResult(
            tool_id=self.tool_id,
            output_paths=[contigs],
            metrics=metrics,
            duration_seconds=time.time() - t0,
        )
