"""Full pipeline orchestrator: coordinates all agents."""

from pathlib import Path
from hyphae.manifest import Manifest
from hyphae.agents.taxonomy import TaxonomyAgent
from hyphae.agents.bgc_discovery import BGCDiscoveryAgent
from hyphae.agents.structure import StructureInferenceAgent
from hyphae.agents.docking import TargetDockingAgent
from hyphae.agents.critic import CriticAgent
from hyphae.agents.literature import LiteratureAgent
from hyphae.agents.reporter import ReporterAgent


class FullOrchestrator:
    """Orchestrates the complete antifungal discovery pipeline."""

    def __init__(self, knowledge_cache: dict | None = None, target_pack: dict | None = None):
        self.knowledge_cache = knowledge_cache or {}
        self.target_pack = target_pack or self._default_targets()

    def _default_targets(self) -> dict:
        """Default antifungal target pack."""
        return {
            "candida_albicans": {
                "CYP51": {"description": "Lanosterol 14α-demethylase (azole target)"},
                "FKS": {"description": "β-1,3-glucan synthase (echinocandin target)"},
                "Hsp90": {"description": "Heat shock protein (exploratory)"},
            },
            "aspergillus_fumigatus": {
                "CYP51A": {"description": "CYP51 (azole target)"},
            }
        }

    def run(
        self,
        manifest: Manifest,
        target_pathogen: str,
        output_dir: Path = Path("report"),
    ) -> Manifest:
        """Execute the full pipeline."""
        print(f"🧬 Starting antifungal discovery pipeline...")

        # Stage 1: Taxonomy & BGC Discovery
        print("📊 Stage 1: Taxonomy & BGC Discovery...")
        tax = TaxonomyAgent()
        manifest = tax.analyze(manifest, target_pathogen)
        
        bgc = BGCDiscoveryAgent()
        manifest = bgc.discover(manifest)

        # Stage 2: Structure & Docking
        print("🧪 Stage 2: Structure Inference & Docking...")
        struct = StructureInferenceAgent()
        manifest = struct.infer(manifest)
        
        dock = TargetDockingAgent()
        manifest = dock.dock(manifest, self.target_pack)

        # Stage 3: Validation & Literature
        print("✅ Stage 3: Critic Review & Literature Search...")
        critic = CriticAgent()
        manifest = critic.review(manifest)
        
        lit = LiteratureAgent()
        manifest = lit.cite(manifest, self.knowledge_cache)

        # Stage 4: Reporting
        print("📝 Stage 4: Report Generation...")
        reporter = ReporterAgent()
        reporter.generate_report(manifest, output_dir)

        print(f"✅ Pipeline complete. Report: {output_dir}")
        return manifest
