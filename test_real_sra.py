import sys
sys.path.insert(0, 'src')

from pathlib import Path
from hyphae.manifest import Manifest
from hyphae.runtime.orchestrator import FullOrchestrator

intent = {
    "sample_sources": [
        {
            "kind": "sra",
            "identifier": "SRR8813623",
            "paired": True,
            "metadata": {"sample_label": "respiratory_candida_1"}
        },
        {
            "kind": "sra", 
            "identifier": "SRR8813624",
            "paired": True,
            "metadata": {"sample_label": "respiratory_candida_2"}
        },
    ],
    "target_pathogen": "candida_albicans",
    "ecosystem": "respiratory_tract",
}

manifest = Manifest(run_id="real_sra_run_001", intent=intent)

orch = FullOrchestrator()
manifest = orch.run(
    manifest,
    target_pathogen="candida_albicans",
    output_dir=Path("report_real_sra"),
    use_real_tools=True
)

print("Real SRA pipeline complete")
