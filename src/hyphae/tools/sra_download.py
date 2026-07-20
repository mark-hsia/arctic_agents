# src/hyphae/tools/sra_download.py
from pathlib import Path
from typing import Any

from hyphae.tools.base import Tool, ToolRunResult


class SraDownloadTool(Tool):
    """
    Mock downloader that creates empty FASTQ files for any accession.
    This enables the Hyphae pipeline to run without contacting NCBI.
    """
    tool_id = "sra-download"

    def run(self, **kwargs: Any) -> ToolRunResult:
        accession: str = kwargs["accession"]
        outdir: str | None = kwargs.get("outdir")
        # Determine the output directory (use the provided outdir or a temp one)
        out_path = Path(outdir) if outdir else Path.cwd() / "sra_mock"
        out_path.mkdir(parents=True, exist_ok=True)

        # Create two empty FASTQ files to mimic paired-end data.
        fastq_files: list[str] = []
        for i in (1, 2):
            fp = out_path / f"{accession}_{i}.fastq"
            fp.touch()                     # creates an empty file
            fastq_files.append(str(fp))

        return ToolRunResult(
            tool_id=self.tool_id,
            output_paths=fastq_files,
            tool_version="mock-v0.1",
        )
