"""SRA / ENA read fetcher.

Wraps ``fasterq-dump`` from sra-tools. Falls back to a documented unavailable
error so the Coordinator can decide whether to skip the sample or retry with
another source.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .base import Tool, ToolRunResult, ToolUnavailable, run_shell


class FasterqDump(Tool):
    tool_id = "reads.fetch"
    binary = "fasterq-dump"

    def version(self) -> str | None:
        try:
            r = run_shell([self.binary, "--version"], check=False)  # type: ignore[list-item]
            return r.stdout.strip().splitlines()[-1] if r.stdout else None
        except Exception:  # pragma: no cover
            return None

    def run(self, **kwargs: Any) -> ToolRunResult:
        accession: str = kwargs["accession"]
        outdir: Path = Path(kwargs["outdir"])
        threads: int = int(kwargs.get("threads", 4))
        outdir.mkdir(parents=True, exist_ok=True)
        if not self.is_available():
            raise ToolUnavailable("fasterq-dump not on PATH")
        t0 = time.time()
        run_shell(
            [self.binary, accession, "--threads", str(threads), "--outdir", str(outdir), "--split-files"],  # type: ignore[list-item]
        )
        outputs = sorted(outdir.glob(f"{accession}*.fastq"))
        return ToolRunResult(
            tool_id=self.tool_id,
            output_paths=outputs,
            metrics={"n_files": len(outputs)},
            duration_seconds=time.time() - t0,
            tool_version=self.version(),
        )


class LocalFastqAdapter(Tool):
    """Pseudo-tool for ``kind="local_fastq"`` sample sources. Always available
    when the file exists; just returns the paths."""

    tool_id = "reads.fetch"

    def is_available(self) -> bool:
        return True

    def run(self, **kwargs: Any) -> ToolRunResult:
        paths = [Path(p) for p in kwargs["paths"]]
        for p in paths:
            if not p.is_file():
                raise ToolUnavailable(f"Local FASTQ missing: {p}")
        return ToolRunResult(
            tool_id=self.tool_id,
            output_paths=paths,
            metrics={"n_files": len(paths)},
            tool_version="local",
        )
