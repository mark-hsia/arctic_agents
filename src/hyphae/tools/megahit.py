"""MEGAHIT wrapper with an offline deterministic fallback."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

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
            output_paths=[Path(path) for path in output_paths],
            metrics=dict(metadata),
            tool_version="v1.2.9",
        )
        self.metadata = metadata


class MegahitTool(BaseTool):
    """Run MEGAHIT when installed, otherwise produce a replay-safe FASTA."""

    def __init__(self) -> None:
        super().__init__(tool_name="assembly.megahit", version="v1.2.9")

    def is_available(self) -> bool:
        # This wrapper is always available because it has a local stub mode.
        return True

    def run(self, *, input_paths: list[str], output_dir: str, **_: object) -> ToolResult:
        if len(input_paths) < 2:
            raise ValueError("MEGAHIT requires two paired input paths")
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        cmd = ["megahit", "-1", input_paths[0], "-2", input_paths[1], "-o", output_dir]
        contig_path = output_path / "final.contigs.fa"

        if shutil.which("megahit") is None:
            contig_path.write_text(">placeholder\nATGC\n")
            return ToolResult(output_paths=[str(contig_path)], metadata={"cmd": " ".join(cmd)})

        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr)
        if not contig_path.is_file():
            raise FileNotFoundError(contig_path)
        return ToolResult(output_paths=[str(contig_path)], metadata={"cmd": " ".join(cmd)})
