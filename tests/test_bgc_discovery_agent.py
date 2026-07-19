"""Focused tests for BGC Discovery input handling."""

from __future__ import annotations

from pathlib import Path

from hyphae.agents.bgc_discovery import BGCDiscoveryAgent
from hyphae.runner import make_run
from hyphae.state import MAG, Intent, RunState
from hyphae.tools.base import Tool, ToolRunResult
from hyphae.tools.registry import ToolRegistry
from hyphae.workflows.runner import StepSpec, WorkflowRunner


class CapturingRunner(WorkflowRunner):
    """Return a small antiSMASH call while retaining its requested input."""

    def __init__(self) -> None:
        self.steps: list[StepSpec] = []

    def run(self, tool: Tool | None, step: StepSpec) -> ToolRunResult:
        self.steps.append(step)
        return ToolRunResult(
            tool_id=step.tool_id,
            metrics={
                "clusters": [
                    {
                        "contig": "contig_0",
                        "start": 10,
                        "end": 1000,
                        "product": "T1PKS",
                    }
                ]
            },
        )


def test_bgc_discovery_resolves_mag_fasta_from_artifact_store(tmp_path: Path) -> None:
    run, initial = make_run(tmp_path, Intent(), tool_registry=ToolRegistry())
    fasta_source = tmp_path / "assembly.fasta"
    fasta_source.write_text(">contig_0\nACGT\n")
    fasta_artifact = run.artifact_store.put_path(
        fasta_source,
        producer_agent="assembly",
        run_id=run.run_id,
        mime_type="text/x-fasta",
    )
    runner = CapturingRunner()
    run.runner = runner
    state = RunState.model_validate(
        {
            **initial.model_dump(),
            "artifacts": [fasta_artifact.model_dump()],
            "mags": [
                MAG(
                    mag_id="M_test",
                    sample_id="S_test",
                    binner="metabat2",
                    fasta_artifact_id=fasta_artifact.artifact_id,
                    is_fungal=True,
                ).model_dump()
            ],
        }
    )

    patch = BGCDiscoveryAgent().step(state, run.context())

    assert runner.steps[0].kwargs["fasta"] == str(run.artifact_store.resolve(fasta_artifact))
    assert patch.bgcs is not None
    assert len(patch.bgcs) == 1
