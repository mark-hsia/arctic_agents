"""Megahit assembler wrapper."""

import subprocess
from pathlib import Path
from typing import Any
from .base import Tool, ToolRunResult


class MegahitTool(Tool):
    """MEGAHIT wrapper that returns only real assembly output."""

    def __init__(self) -> None:
        self.tool_id = "assembly.megahit"
        self._version = "v1.2.9"

    @property
    def version(self) -> str:
        return self._version

    def is_available(self) -> bool:
        try:
            return subprocess.run(["megahit", "--version"], capture_output=True, timeout=5).returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def run(self, **kwargs: Any) -> ToolRunResult:
        input_paths = kwargs.get("input_paths", [])
        output_dir = kwargs.get("output_dir", "megahit_out")
        threads = kwargs.get("threads", 4)

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        if not input_paths:
            raise ValueError("MEGAHIT requires at least one FASTQ input path")

        contig_path = out / "final.contigs.fa"
        cmd = (
            ["megahit", "-1", input_paths[0], "-2", input_paths[1], "-o", str(out), "-t", str(threads)]
            if len(input_paths) >= 2
            else ["megahit", "-r", input_paths[0], "-o", str(out), "-t", str(threads)]
        )
        try:
            version = subprocess.run(["megahit", "--version"], capture_output=True, timeout=5, check=False)
            if version.returncode != 0:
                raise FileNotFoundError("MEGAHIT binary not functional")
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3600)
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(
                "MEGAHIT failed. Install it with `conda install -c bioconda megahit` "
                f"and verify input FASTQs. Cause: {exc}"
            ) from exc
        if not contig_path.is_file() or contig_path.stat().st_size == 0:
            raise RuntimeError("MEGAHIT completed without final.contigs.fa")

        return ToolRunResult(
            tool_id=self.tool_id,
            output_paths=[contig_path],
            metrics={"source": "real"},
            tool_version=self.version,
        )
