"""MAG QC wrappers (CheckM2, BUSCO) and EukRep eukaryote detection."""

from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Any

from .base import Tool, ToolRunResult, ToolUnavailable, run_shell


class CheckM2(Tool):
    tool_id = "magqc.checkm2"
    binary = "checkm2"

    def run(self, **kwargs: Any) -> ToolRunResult:
        if not self.is_available():
            raise ToolUnavailable("checkm2 not on PATH")
        bins_dir: Path = Path(kwargs["bins_dir"])
        outdir: Path = Path(kwargs["outdir"])
        outdir.mkdir(parents=True, exist_ok=True)
        threads: int = int(kwargs.get("threads", 4))
        cmd = [self.binary, "predict", "--input", str(bins_dir), "--output-directory", str(outdir), "-t", str(threads)]  # type: ignore[list-item]
        t0 = time.time()
        run_shell(cmd)
        report = outdir / "quality_report.tsv"
        per_bin: dict[str, dict[str, float]] = {}
        if report.is_file():
            with report.open() as fh:
                reader = csv.DictReader(fh, delimiter="\t")
                for row in reader:
                    name = row.get("Name") or row.get("name") or ""
                    per_bin[name] = {
                        "completeness": float(row.get("Completeness", "0") or 0),
                        "contamination": float(row.get("Contamination", "0") or 0),
                    }
        return ToolRunResult(
            tool_id=self.tool_id,
            output_paths=[report] if report.is_file() else [],
            metrics={"per_bin": per_bin},
            duration_seconds=time.time() - t0,
        )


class Busco(Tool):
    tool_id = "magqc.busco"
    binary = "busco"

    def run(self, **kwargs: Any) -> ToolRunResult:
        if not self.is_available():
            raise ToolUnavailable("busco not on PATH")
        fasta: Path = Path(kwargs["fasta"])
        outdir: Path = Path(kwargs["outdir"])
        lineage: str = kwargs.get("lineage", "ascomycota_odb10")
        threads: int = int(kwargs.get("threads", 4))
        outdir.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.binary,  # type: ignore[list-item]
            "-i", str(fasta),
            "-o", fasta.stem,
            "--out_path", str(outdir),
            "-l", lineage,
            "-m", "genome",
            "-c", str(threads),
            "--offline",
        ]
        t0 = time.time()
        run_shell(cmd)
        # Parse short_summary.* for completeness
        short = next((outdir / fasta.stem).glob("short_summary.*.txt"), None)
        complete: float | None = None
        if short is not None:
            for line in short.read_text().splitlines():
                if "(C)" in line and "%" in line:
                    try:
                        complete = float(line.strip().split("%")[0].split(":")[-1])
                    except ValueError:  # pragma: no cover
                        pass
        return ToolRunResult(
            tool_id=self.tool_id,
            output_paths=[short] if short else [],
            metrics={"complete_pct": complete, "lineage": lineage},
            duration_seconds=time.time() - t0,
        )


class EukRep(Tool):
    tool_id = "domain.eukrep"
    binary = "EukRep"

    def run(self, **kwargs: Any) -> ToolRunResult:
        if not self.is_available():
            raise ToolUnavailable("EukRep not on PATH")
        contigs: Path = Path(kwargs["contigs"])
        outdir: Path = Path(kwargs["outdir"])
        outdir.mkdir(parents=True, exist_ok=True)
        euk_out = outdir / "eukaryote.fa"
        prok_out = outdir / "prokaryote.fa"
        cmd = [
            self.binary,  # type: ignore[list-item]
            "-i", str(contigs),
            "-o", str(euk_out),
            "--prokarya", str(prok_out),
        ]
        t0 = time.time()
        run_shell(cmd)
        return ToolRunResult(
            tool_id=self.tool_id,
            output_paths=[euk_out, prok_out],
            metrics={},
            duration_seconds=time.time() - t0,
        )
