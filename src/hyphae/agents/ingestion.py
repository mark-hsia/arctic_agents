"""Ingestion agent.

Fetches reads (SRA accession or local path) and runs basic QC. Decisions:
  * accept paired vs. single-end inputs;
  * subsample decisions are logged; no data are fabricated.
  * mark a sample failed when QC verdict is fail.

Heavy work (fastp) is delegated to the workflow runner.
"""

from __future__ import annotations

from pathlib import Path

from ..ids import short_hash
from ..state import QcVerdict, RunState, RunStatePatch, Sample, SampleSource
from ..tools.base import ToolUnavailable
from ..workflows.runner import StepSpec
from .base import Agent, AgentContext


class IngestionAgent(Agent):
    name = "ingestion"
    reads = ("intent",)
    writes = ("samples",)
    tools = ("reads.fetch", "reads.qc")

    def step(self, state: RunState, ctx: AgentContext) -> RunStatePatch:
        new_samples: list[Sample] = []
        new_artifacts = []
        new_rationales = []

        for source in state.intent.sample_sources:
            sample_id = self._sample_id(source)
            ctx.logger.info("ingest %s (%s)", sample_id, source.identifier)
            sample, art_list, rat_list = self._ingest_one(sample_id, source, ctx)
            new_samples.append(sample)
            new_artifacts.extend(art_list)
            new_rationales.extend(rat_list)

        ctx.record(artifacts=new_artifacts, rationales=new_rationales)
        patch = RunStatePatch(
            samples=new_samples or None,
            artifacts=new_artifacts or None,
            rationales=new_rationales or None,
        )
        self.validate_patch(patch)
        return patch

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _sample_id(source: SampleSource) -> str:
        return f"S_{short_hash(source.kind, source.identifier)}"

    def _ingest_one(self, sample_id: str, source: SampleSource, ctx: AgentContext):
        artifacts = []
        rationales = []
        sample_workdir = ctx.workdir / "ingestion" / sample_id
        sample_workdir.mkdir(parents=True, exist_ok=True)

        try:
            if source.kind == "local_fastq":
                paths = source.metadata.get("paths") or [source.identifier]
                from ..tools.sra import LocalFastqAdapter

                fetch_result = LocalFastqAdapter().run(paths=paths)
            else:
                fetch_step = StepSpec(
                    step_id=f"ingest.fetch.{sample_id}",
                    tool_id="reads.fetch",
                    kwargs={
                        "accession": source.identifier,
                        "outdir": str(sample_workdir / "raw"),
                    },
                )
                fetch_result = ctx.runner.execute(fetch_step, ctx.tools)

            for p in fetch_result.output_paths:
                if Path(p).is_file():
                    art = ctx.artifact_store.put_path(
                        p,
                        producer_agent=self.name,
                        run_id=ctx.run_id,
                        tool_version=fetch_result.tool_version,
                        mime_type="text/x-fastq",
                    )
                    artifacts.append(art)
            qc_verdict = QcVerdict.pass_
            qc_artifact_id: str | None = None
            n_reads: int | None = None

            try:
                if fetch_result.output_paths:
                    in1 = fetch_result.output_paths[0]
                    in2 = (
                        fetch_result.output_paths[1]
                        if source.paired and len(fetch_result.output_paths) > 1
                        else None
                    )
                    qc_step = StepSpec(
                        step_id=f"ingest.qc.{sample_id}",
                        tool_id="reads.qc",
                        kwargs={
                            "in1": str(in1),
                            "in2": str(in2) if in2 else None,
                            "outdir": str(sample_workdir / "qc"),
                        },
                    )
                    qc_result = ctx.runner.execute(qc_step, ctx.tools)
                    n_reads = qc_result.metrics.get("total_reads")
                    q30 = qc_result.metrics.get("q30_rate")
                    if q30 is not None:
                        if q30 < 0.7:
                            qc_verdict = QcVerdict.fail
                        elif q30 < 0.85:
                            qc_verdict = QcVerdict.marginal
                    if qc_result.output_paths:
                        qc_art = ctx.artifact_store.put_path(
                            qc_result.output_paths[-1],  # JSON report
                            producer_agent=self.name,
                            run_id=ctx.run_id,
                            tool_version=qc_result.tool_version,
                            mime_type="application/json",
                            parent_ids=[a.artifact_id for a in artifacts],
                        )
                        artifacts.append(qc_art)
                        qc_artifact_id = qc_art.artifact_id
            except ToolUnavailable as exc:
                rationales.append(
                    ctx.make_rationale(
                        self.name,
                        claim=f"QC deferred for {sample_id}: {exc}. Sample marked marginal pending re-run.",
                        evidence_artifact_ids=[a.artifact_id for a in artifacts],
                    )
                )
                qc_verdict = QcVerdict.marginal

            sample = Sample(
                sample_id=sample_id,
                source=source,
                raw_artifact_ids=[a.artifact_id for a in artifacts if a.artifact_id != qc_artifact_id],
                qc_artifact_id=qc_artifact_id,
                qc_verdict=qc_verdict,
                n_reads=n_reads,
                metadata=dict(source.metadata),
            )
            rationales.append(
                ctx.make_rationale(
                    self.name,
                    claim=(
                        f"Ingested {sample_id} from {source.kind}:{source.identifier}; "
                        f"QC verdict={qc_verdict.value}."
                    ),
                    evidence_artifact_ids=[a.artifact_id for a in artifacts],
                )
            )
            return sample, artifacts, rationales

        except ToolUnavailable as exc:
            ctx.logger.warning("ingestion deferred for %s: %s", sample_id, exc)
            sample = Sample(
                sample_id=sample_id,
                source=source,
                raw_artifact_ids=[],
                qc_verdict=QcVerdict.marginal,
                metadata=dict(source.metadata),
            )
            rationales.append(
                ctx.make_rationale(
                    self.name,
                    claim=(
                        f"Ingestion deferred for {sample_id}: {exc}. "
                        "Sample recorded with no raw artifacts."
                    ),
                )
            )
            return sample, artifacts, rationales
