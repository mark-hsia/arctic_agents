"""Full pipeline orchestrator: coordinates all agents."""

from pathlib import Path
from hyphae.manifest import Manifest
from hyphae.agents.assembly import AssemblyAgent
from hyphae.agents.taxonomy import TaxonomyAgent
from hyphae.agents.bgc_discovery import BGCDiscoveryAgent
from hyphae.agents.structure import StructureInferenceAgent
from hyphae.agents.docking import TargetDockingAgent
from hyphae.agents.critic import CriticAgent
from hyphae.agents.literature import LiteratureAgent
from hyphae.agents.reporter import ReporterAgent


class FullOrchestrator:
    """Orchestrates the complete antifungal discovery pipeline."""

    def __init__(self, knowledge_cache: dict = None, target_pack: dict = None):
        self.knowledge_cache = knowledge_cache or {}
        self.target_pack = target_pack or self._default_targets()

    def _default_targets(self) -> dict:
        """Default antifungal target pack."""
        return {
            "candida_albicans": {
                "CYP51": {"description": "Lanosterol 14a-demethylase (azole target)"},
                "FKS": {"description": "b-1,3-glucan synthase (echinocandin target)"},
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
        use_real_tools: bool = False,
    ) -> Manifest:
        """Execute the real-only pipeline or fail with an actionable error."""
        if not use_real_tools:
            raise ValueError(
                "Real pipeline requires use_real_tools=True; synthetic and heuristic execution paths are disabled."
            )
        print("REAL PIPELINE: FASTQ → Assembly → local evidence detection → Structures → Docking")

        print("Stage 1: Assembly and local BGC keyword detection...")
        asm = AssemblyAgent()
        manifest = asm.assemble(manifest, output_dir / "assembly")
        tax = TaxonomyAgent()
        manifest = tax.analyze(manifest, target_pathogen)
        
        print("Starting BGC discovery without external APIs...\n")
        bgc = BGCDiscoveryAgent(max_wait_seconds=7200, poll_interval_seconds=30)
        manifest = bgc.discover(manifest)

        print(f"Found {len(manifest.final_state.get('bgcs', []))} real BGCs")
        if not manifest.final_state.get("bgcs"):
            raise RuntimeError(
                "antiSMASH returned no BGCs. Verify contigs, antiSMASH API availability, and fungal input quality."
            )
        print("Stage 2: Structure and Docking...")
        struct = StructureInferenceAgent()
        manifest = struct.infer(manifest, use_antismash=use_real_tools)
        
        dock = TargetDockingAgent()
        manifest = dock.dock(manifest, self.target_pack, use_vina=use_real_tools)

        print("Stage 3: Critic Review and Literature Search...")
        critic = CriticAgent()
        manifest = critic.review(manifest)
        
        lit = LiteratureAgent()
        manifest = lit.cite(manifest, self.knowledge_cache)

        print("Stage 4: Report Generation...")
        reporter = ReporterAgent()
        reporter.generate_report(manifest, output_dir)

        print("Pipeline complete. Report: " + str(output_dir))
        return manifest
