# src/hyphae/tools/sra_download.py
from pathlib import Path
from typing import Any

from hyphae.tools.base import Tool, ToolRunResult


class SraDownloadTool(Tool):
    """
    Fetch an SRA run using real local or remote acquisition methods.
    """
    tool_id = "sra-download"

    def run(self, **kwargs: Any) -> ToolRunResult:
        from hyphae.data.sra_fetcher import SraFetcher

        accession = str(kwargs.get("accession", "unknown"))
        output_dir = str(kwargs.get("output_dir", kwargs.get("outdir", "downloads")))
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        fetcher = SraFetcher(cache_dir=output_dir)
        fetched = fetcher.fetch(accession, paired=True)
        paths = list(fetched) if isinstance(fetched, tuple) else [fetched]
        if len(paths) != 2:
            raise RuntimeError(f"Expected paired FASTQ files for {accession}, got {len(paths)}")
        return ToolRunResult(
            tool_id=self.tool_id,
            output_paths=[Path(path) for path in paths],
            metrics={"files": len(paths), "accession": accession},
            tool_version=self.version(),
        )
