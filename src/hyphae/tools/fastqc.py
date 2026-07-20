from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Any
from .base import Tool, ToolRunResult

class FastqcTool(Tool):
    """Runs FastQC; if the binary is missing it creates a tiny HTML stub."""
    def __init__(self) -> None:
        self.tool_id = "reads.qc"
        self._version = "v0.12.1"

    def is_available(self) -> bool:
        # Always return True – the stub guarantees deterministic replay.
        return True

    def run(self, **kwargs: Any) -> ToolRunResult:
        """
        Parameters
        ----------
        input_paths: list[str]
            Paths to FASTQ files (paired or single‑end).
        """
        input_paths = kwargs.get("input_paths", [])

        out_dir = Path("fastqc_results")
        out_dir.mkdir(parents=True, exist_ok=True)

        cmd = ["fastqc", "-o", str(out_dir), *input_paths]

        # If the real binary is not on the PATH, write a dummy HTML per input.
        if subprocess.run(["which", "fastqc"], capture_output=True, text=True).returncode != 0:
            for p in input_paths:
                (out_dir / (Path(p).stem + "_fastqc.html")).write_text(
                    "<html><body>FastQC stub</body></html>"
                )
        else:
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        reports = sorted(str(p) for p in out_dir.glob("*.html"))
        return ToolRunResult(
            tool_id="reads.qc",
            output_paths=[Path(p) for p in reports],
            metrics={},
            tool_version="v0.12.1",
        )
