"""fastp QC + trimming wrapper."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .base import Tool, ToolRunResult, ToolUnavailable, run_shell


class Fastp(Tool):
    tool_id = "reads.qc"
    binary = "fastp"

    def version(self) -> str | None:
        try:
            r = run_shell([self.binary, "--version"], check=False)  # type: ignore[list-item]
            return (r.stderr or r.stdout).strip().splitlines()[-1] if (r.stdout or r.stderr) else None
        except Exception:  # pragma: no cover
            return None

    def run(self, **kwargs: Any) -> ToolRunResult:
        in1: Path = Path(kwargs["in1"])
        in2: Path | None = Path(kwargs["in2"]) if kwargs.get("in2") else None
        outdir: Path = Path(kwargs["outdir"])
        outdir.mkdir(parents=True, exist_ok=True)
        if not self.is_available():
            raise ToolUnavailable("fastp not on PATH")

        out1 = outdir / f"{in1.stem}.qc.fastq.gz"
        out2 = outdir / f"{in2.stem}.qc.fastq.gz" if in2 else None
        report_json = outdir / "fastp.json"
        report_html = outdir / "fastp.html"

        cmd = [self.binary, "-i", str(in1), "-o", str(out1)]  # type: ignore[list-item]
        if in2 and out2:
            cmd += ["-I", str(in2), "-O", str(out2)]
        cmd += ["-j", str(report_json), "-h", str(report_html)]
        t0 = time.time()
        run_shell(cmd)

        metrics: dict[str, Any] = {}
        if report_json.is_file():
            try:
                report = json.loads(report_json.read_text())
                summary = report.get("summary", {})
                after = summary.get("after_filtering", {})
                metrics["q20_rate"] = after.get("q20_rate")
                metrics["q30_rate"] = after.get("q30_rate")
                metrics["total_reads"] = after.get("total_reads")
                metrics["read_length_mean"] = (
                    (after.get("read1_mean_length") or 0) + (after.get("read2_mean_length") or 0)
                ) / (2 if after.get("read2_mean_length") else 1)
            except Exception:  # pragma: no cover
                pass

        outputs = [p for p in (out1, out2, report_json, report_html) if p is not None]
        return ToolRunResult(
            tool_id=self.tool_id,
            output_paths=outputs,
            metrics=metrics,
            duration_seconds=time.time() - t0,
            tool_version=self.version(),
        )
