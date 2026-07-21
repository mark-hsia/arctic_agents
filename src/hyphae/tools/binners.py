"""MAG binner wrappers (MetaBAT2, CONCOCT) and DAS Tool consensus.

These are thin wrappers — heavy work is delegated to the binaries. Each tool
emits a directory of FASTA bins; the agent layer decides which to advance.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .base import Tool, ToolRunResult, ToolUnavailable, run_shell


class MetaBAT2(Tool):
    tool_id = "binning.metabat2"
    binary = "metabat2"

    def run(self, **kwargs: Any) -> ToolRunResult:
        contigs: Path = Path(kwargs["contigs"])
        depths: Path = Path(kwargs["depths"])  # jgi_summarize_bam_contig_depths output
        outdir: Path = Path(kwargs["outdir"])
        outdir.mkdir(parents=True, exist_ok=True)
        if not self.is_available():
            raise ToolUnavailable("metabat2 not on PATH")
        out_prefix = outdir / "bin"
        cmd = [self.binary, "-i", str(contigs), "-a", str(depths), "-o", str(out_prefix)]  # type: ignore[list-item]
        t0 = time.time()
        run_shell(cmd)
        bins = sorted(outdir.glob("bin.*.fa"))
        return ToolRunResult(
            tool_id=self.tool_id,
            output_paths=bins,
            metrics={"n_bins": len(bins)},
            duration_seconds=time.time() - t0,
        )


class CONCOCT(Tool):
    tool_id = "binning.concoct"
    binary = "concoct"

    def run(self, **kwargs: Any) -> ToolRunResult:
        if not self.is_available():
            raise ToolUnavailable("concoct not on PATH")
        # Real wiring (cut_up_fasta, concoct_coverage_table, concoct,
        # merge_cutup_clustering, extract_fasta_bins) is multi-step and
        # CONCOCT is currently implemented only in the Snakemake workflow.
        outdir: Path = Path(kwargs["outdir"])
        outdir.mkdir(parents=True, exist_ok=True)
        raise ToolUnavailable(
            "CONCOCT is wired only via the Snakemake workflow runner in this release"
        )


class DASTool(Tool):
    tool_id = "binning.das_tool"
    binary = "DAS_Tool"

    def run(self, **kwargs: Any) -> ToolRunResult:
        if not self.is_available():
            raise ToolUnavailable("DAS_Tool not on PATH")
        contigs: Path = Path(kwargs["contigs"])
        bin_tables: list[Path] = [Path(p) for p in kwargs["bin_tables"]]
        labels: list[str] = list(kwargs["labels"])
        outdir: Path = Path(kwargs["outdir"])
        outdir.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.binary,  # type: ignore[list-item]
            "-i", ",".join(str(p) for p in bin_tables),
            "-c", str(contigs),
            "-l", ",".join(labels),
            "-o", str(outdir / "das"),
            "--write_bins",
        ]
        t0 = time.time()
        run_shell(cmd)
        bins = sorted((outdir / "das_DASTool_bins").glob("*.fa"))
        return ToolRunResult(
            tool_id=self.tool_id,
            output_paths=bins,
            metrics={"n_bins": len(bins)},
            duration_seconds=time.time() - t0,
        )
