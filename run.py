#!/usr/bin/env python3
"""Run Hyphae on discovered real Candida or Aspergillus SRA data.

This command intentionally never creates test data. It exits with a clear
remediation message when SRA access or required scientific tooling is absent.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from hyphae.agents import CriticAgent, LiteratureAgent, ReporterAgent, StructureInferenceAgent, TargetDockingAgent
from hyphae.agents.coordinator import Coordinator
from hyphae.runner import make_run
from hyphae.state import Budget, Intent, SampleSource, TargetPathogen, apply_patch
from hyphae.tools.sra_download import SraDownloadTool
from hyphae.tools.sra_metadata_scraper import SRAMetadataScraper

LOG = logging.getLogger("hyphae.run")
FALLBACK_ACCESSIONS = ("SRX34462262", "SRX33995160")
TARGET_ORGANISMS = ("Candida albicans", "Aspergillus fumigatus")


def select_real_run(scraper: SRAMetadataScraper) -> dict:
    """Discover an organism-associated run first; use supplied accessions only if needed."""
    errors: list[str] = []
    for organism in TARGET_ORGANISMS:
        try:
            records = scraper.search_organism(organism, limit=1)
            if records:
                LOG.info("Selected discovered %s run %s", organism, records[0]["accession"])
                return records[0]
        except Exception as exc:
            errors.append(f"{organism}: {exc}")
    for accession in FALLBACK_ACCESSIONS:
        try:
            record = scraper.fetch(accession)
            LOG.warning("Discovery failed; using configured real SRA accession %s", accession)
            return record
        except Exception as exc:
            errors.append(f"{accession}: {exc}")
    raise RuntimeError("Could not discover or resolve a real Candida/Aspergillus SRA record. " + " | ".join(errors))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root = Path(__file__).resolve().parent
    workdir = root / "tmp" / "real_sra_run"
    metadata = select_real_run(SRAMetadataScraper(root / ".hyphae_cache"))
    accession = str(metadata["accession"])
    try:
        download = SraDownloadTool().run(
            sra_accessions=[accession], output_dir=workdir / "fastq", use_stubs=False
        )
    except Exception as exc:
        LOG.error("Real FASTQ download failed for %s: %s", accession, exc)
        return 2
    if not download.output_paths or not all(path.is_file() for path in download.output_paths):
        LOG.error("Real FASTQ download returned no usable files for %s", accession)
        return 2

    intent = Intent(
        target_pathogen=TargetPathogen.candida_albicans,
        ecosystem=str(metadata["organism"]),
        sample_sources=[SampleSource(
            kind="local_fastq", identifier=accession,
            paired=metadata["library_type"] == "PAIRED",
            metadata={"paths": [str(path) for path in download.output_paths], "sra_metadata": metadata},
        )],
        budget=Budget(max_tokens=500_000, max_dollars=25.0, max_wall_clock_seconds=7_200),
        deterministic=True,
        notes="Real-data-only Hyphae run",
    )
    run, initial = make_run(workdir, intent, deterministic=True)
    result = Coordinator(run.context()).run(initial)
    state = result.final_state
    for agent in (StructureInferenceAgent(), TargetDockingAgent(), LiteratureAgent(), CriticAgent()):
        state = apply_patch(state, agent.step(state, run.context()))
    ReporterAgent().step(state, run.context())

    candidates = [entry for entries in state.docking.values() for entry in entries]
    report_dir = workdir / "report"
    print(f"Audit report: {report_dir}")
    print(f"Real input: {accession} ({metadata['organism']})")
    print(f"BGCs: {len(state.bgcs)}; docking results: {len(candidates)}")
    if not candidates:
        LOG.error("No real, provenance-backed docking candidates were produced. Review deferred rationales in %s.", report_dir / "run_card.json")
        return 3
    for entry in sorted(candidates, key=lambda item: item.score)[:10]:
        print(f"{entry.structure_id}\t{entry.target_name}\t{entry.score:.3f}\t{entry.method}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
