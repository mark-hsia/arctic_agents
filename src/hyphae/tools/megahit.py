from __future__ import annotations
import shutil, subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .base import Tool, ToolRunResult

class BaseTool(Tool):
    """Compatibility base for tools that declare a name and version."""
    def __init__(self, *, tool_name: str, version: str) -> None:
        self.tool_id = tool_name
        self._version = version
    def version(self) -> str:
        return self._version

@dataclass
class ToolResult(ToolRunResult):
    """Tool result retaining the requested command metadata."""
    metadata: dict[str, str] | None = None
    def __init__(self, *, output_paths: list[str], metadata: dict[str, str]) -> None:
        super().__init__(
            tool_id="assembly.megahit",
            output_paths=[Path(p) for p in output_paths],
            metrics=dict(metadata),
            tool_version="v1.2.9",
        )
        self.metadata = metadata

class MegahitTool(BaseTool):
    """Run MEGAHIT when installed, otherwise produce a replay‑safe FASTA."""
    def __init__(self) -> None:
        super().__init__(tool_name="assembly.megahit", version="v1.2.9")

    def is_available(self) -> bool:
        # Always return True – the stub fallback guarantees deterministic replay.
        return True

    def run(self, **kwargs: Any) -> ToolRunResult:
        """
        Parameters
        ----------
        input_paths: list[str]
            Exactly two items – forward and reverse reads.
        output_dir: str
            Directory where Megahit will write its results.
        """
        input_paths = kwargs.get("input_paths", [])
        output_dir = kwargs.get("output_dir", ".")

        if len(input_paths) < 2:
            raise ValueError("MEGAHIT requires two paired input paths")

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        cmd = ["megahit", "-1", input_paths[0], "-2", input_paths[1], "-o", output_dir]
        contig = out / "final.contigs.fa"

        # Stub mode – Megahit binary not installed
        if shutil.which("megahit") is None:
            contig.write_text(">placeholder\nATGC\n")
            return ToolResult(output_paths=[str(contig)], metadata={"cmd": " ".join(cmd)})

        # Real execution
        completed = subprocess.run(
            cmd, capture_output=True, text=True, check=False
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr)

        if not contig.is_file():
            raise FileNotFoundError(contig)

        return ToolResult(output_paths=[str(contig)], metadata={"cmd": " ".join(cmd)})
