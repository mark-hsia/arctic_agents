# src/hyphae/tools/sra_download.py
from pathlib import Path
from typing import Any

from hyphae.tools.base import Tool, ToolRunResult


class SraDownloadTool(Tool):
    """
    Fetch an SRA run, using small labelled fixtures by default for development.
    """
    tool_id = "sra-download"

    def run(self, **kwargs: Any) -> ToolRunResult:
        from hyphae.data.sra_fetcher import SraFetcher
        from hyphae.tools.fastq_stub_generator import FASTQStubGenerator
        from hyphae.tools.sra_metadata_scraper import SRAMetadataScraper

        requested = kwargs.get("sra_accessions", kwargs.get("accession"))
        accessions = [str(item) for item in requested] if isinstance(requested, (list, tuple)) else [str(requested or "")]
        if not all(accessions):
            raise ValueError("accession or sra_accessions is required")
        output_dir = str(kwargs.get("output_dir", kwargs.get("outdir", "downloads")))
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        use_stubs = bool(kwargs.get("use_stubs", True))
        paths: list[str] = []
        metadata: list[dict[str, Any]] = []
        if use_stubs:
            scraper = SRAMetadataScraper(cache_dir=kwargs.get("metadata_cache_dir", ".hyphae_cache"))
            generator = FASTQStubGenerator(seed=int(kwargs.get("seed", 42)))
            for accession in accessions:
                record = scraper.fetch(accession)
                metadata.append(record)
                paired = record["library_type"] == "PAIRED"
                generated = generator.generate_paired(accession, int(kwargs.get("num_stub_reads", 100)), output_dir) if paired else generator.generate_single(accession, int(kwargs.get("num_stub_reads", 100)), output_dir)
                paths.extend(generated)
            rationale = "Generated stub FASTQ for testing"
        else:
            fetcher = SraFetcher(cache_dir=output_dir)
            for accession in accessions:
                fetched = fetcher.fetch(accession, paired=True)
                paths.extend(list(fetched) if isinstance(fetched, tuple) else [fetched])
            rationale = "Downloaded real FASTQ from SRA"
        return ToolRunResult(
            tool_id=self.tool_id,
            output_paths=[Path(path) for path in paths],
            metrics={"files": len(paths), "accessions": accessions, "metadata": metadata, "rationale": rationale, "stub": use_stubs},
            tool_version=self.version(),
        )
