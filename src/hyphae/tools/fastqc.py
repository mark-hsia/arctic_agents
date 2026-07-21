"""FastQC wrapper for read quality control."""

import subprocess
from pathlib import Path
from typing import Any
from .base import Tool, ToolRunResult


class FastqcTool(Tool):
    """Runs FastQC in quiet mode (non-interactive)."""

    def __init__(self) -> None:
        self.tool_id = "reads.qc"
        self._version = "v0.12.1"

    @property
    def version(self) -> str:
        return self._version

    def is_available(self) -> bool:
        """Check if fastqc binary exists."""
        try:
            subprocess.run(
                ["fastqc", "--version"],
                capture_output=True,
                timeout=5,
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def run(self, **kwargs: Any) -> ToolRunResult:
        """Run FastQC in quiet (non-interactive) mode."""
        input_paths = kwargs.get("input_paths", [])
        output_dir = kwargs.get("output_dir", "fastqc_results")

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if not input_paths:
            raise ValueError("FastQC requires at least one input FASTQ path")

        # Run fastqc with --quiet (non-interactive) and --noextract
        cmd = ["fastqc", "--quiet", "--noextract", "-o", str(out_dir), *input_paths]

        try:
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=600,
            )
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(
                "FastQC failed. Install it with `conda install -c bioconda fastqc` "
                f"and verify the FASTQ inputs. Cause: {exc}"
            ) from exc

        # Return results
        reports = sorted(str(p) for p in out_dir.glob("*_fastqc.zip"))
        if not reports:
            raise RuntimeError("FastQC completed without producing a report archive")
        return ToolRunResult(
            tool_id="reads.qc",
            output_paths=[Path(p) for p in reports],
            metrics={"files_processed": len(input_paths)},
            tool_version=self.version,
        )
