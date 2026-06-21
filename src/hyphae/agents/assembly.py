"""Assembly & Binning agent.

Decisions:
  * pick metaSPAdes by default; fall back to MEGAHIT when read count is high
    or memory is tight (heuristic: ``> 50M reads`` or marginal QC).
  * defer assembly when neither assembler is available, recording a rationale.
  * compute assembly stats (N50, total length, n_contigs) on whatever FASTA
    the runner produces — this works for replay-mode too.

Heavy steps are submitted to ``ctx.runner``. Binning + MAG QC follow the same
pattern; v0.1 advances the contigs as a single placeholder MAG when binning
tools are not available, so downstream BGC discovery can still run.
"""

from __future__ import annotations

from pathlib import Path

from ..ids import short_hash
from ..state import (
    MAG,
    AssemblyResult,
    QcVerdict,
    RunState,
    RunStatePatch,
    Sample,
    TaxonomyCall,
)
from ..tools.assemblers import fasta_assembly_stats
from ..tools.base import ToolUnavailable
from ..workflows.runner import StepSpec
from .base import Agent, AgentContext


class AssemblyAgent(Agent):
    name = "assembly"
    reads = ("intent", "samples")
    writes = ("assemblies", "mags", "taxonomy")
    tools = (
        "assembly.metaspades",
        "assembly.megahit",
        "binning.metabat2",
        "binning.concoct",
        "binning.das_tool",
        "magqc.checkm2",
        "magqc.busco",
        "domain.eukrep",
    )

    METASPADES_READ_THRESHOLD = 50_000_000

    def step(self, state: RunState, ctx: AgentContext) -> RunStatePatch:
        new_assemblies: dict[str, AssemblyResult] = {}
        new_mags: list[MAG] = []
        new_taxonomy: dict[str, TaxonomyCall] = {}
        new_artifacts = []
        new_rationales = []

        for sample in state.samples:
            if sample.qc_verdict == QcVerdict.fail:
                new_rationales.append(
                    ctx.make_rationale(
                        self.name,
                        f"Skipping assembly for {sample.sample_id}: QC fail.",
                    )
                )
                continue

            chosen, asm_step = self._choose_assembler(sample, ctx)
            ctx.logger.info("assembly %s -> %s", sample.sample_id, chosen)

            try:
                result = ctx.runner.execute(asm_step, ctx.tools)
            except ToolUnavailable as exc:
                new_rationales.append(
                    ctx.make_rationale(
                        self.name,
                        f"Assembly deferred for {sample.sample_id}: {exc}",
                    )
                )
                continue

            contigs_path = next(
                (p for p in result.output_paths if str(p).endswith((".fasta", ".fa", ".fa.gz"))),
                None,
            )
            stats = result.metrics or {}
            if contigs_path is not None and Path(contigs_path).is_file() and not stats:
                stats = fasta_assembly_stats(Path(contigs_path))

            if contigs_path is not None and Path(contigs_path).is_file():
                contigs_artifact = ctx.artifact_store.put_path(
                    contigs_path,
                    producer_agent=self.name,
                    run_id=ctx.run_id,
                    tool_version=result.tool_version,
                    mime_type="text/x-fasta",
                    parent_ids=sample.raw_artifact_ids,
                )
                new_artifacts.append(contigs_artifact)
                contigs_artifact_id = contigs_artifact.artifact_id
            else:
                # No real file (replay manifests may omit paths but provide metrics).
                contigs_artifact_id = f"art_assembly_{sample.sample_id}"

            assembly = AssemblyResult(
                sample_id=sample.sample_id,
                assembler=chosen,
                assembly_artifact_id=contigs_artifact_id,
                n_contigs=stats.get("n_contigs"),
                total_length=stats.get("total_length"),
                n50=stats.get("n50"),
                largest_contig=stats.get("largest_contig"),
            )
            new_assemblies[sample.sample_id] = assembly
            new_rationales.append(
                ctx.make_rationale(
                    self.name,
                    claim=(
                        f"Assembled {sample.sample_id} with {chosen}: "
                        f"n50={stats.get('n50')}, total={stats.get('total_length')}, "
                        f"n_contigs={stats.get('n_contigs')}."
                    ),
                    evidence_artifact_ids=[contigs_artifact_id]
                    if contigs_artifact_id.startswith("art_") and not contigs_artifact_id.startswith("art_assembly_")
                    else [],
                )
            )

            mag, mag_arts, mag_rats, taxonomy = self._bin_and_qc(
                sample, assembly, contigs_path, ctx
            )
            if mag is not None:
                new_mags.append(mag)
                if taxonomy is not None:
                    new_taxonomy[mag.mag_id] = taxonomy
            new_artifacts.extend(mag_arts)
            new_rationales.extend(mag_rats)

        ctx.record(artifacts=new_artifacts, rationales=new_rationales)
        patch = RunStatePatch(
            assemblies=new_assemblies or None,
            mags=new_mags or None,
            taxonomy=new_taxonomy or None,
            artifacts=new_artifacts or None,
            rationales=new_rationales or None,
        )
        self.validate_patch(patch)
        return patch

    # ------------------------------------------------------------------ helpers

    def _choose_assembler(self, sample: Sample, ctx: AgentContext) -> tuple[str, StepSpec]:
        n_reads = sample.n_reads or 0
        prefer_megahit = (
            n_reads > self.METASPADES_READ_THRESHOLD
            or sample.qc_verdict == QcVerdict.marginal
        )
        outdir = ctx.workdir / "assembly" / sample.sample_id
        # We only know read paths through artifacts; agents don't read filesystem
        # paths directly. For the local-FASTQ case, the metadata carries them.
        paths = sample.source.metadata.get("paths") or []
        in1 = paths[0] if paths else f"/missing/{sample.sample_id}_1.fastq"
        in2 = paths[1] if (sample.source.paired and len(paths) > 1) else None

        if prefer_megahit:
            chosen = "megahit"
            step = StepSpec(
                step_id=f"asm.megahit.{sample.sample_id}",
                tool_id="assembly.megahit",
                kwargs={"in1": in1, "in2": in2, "outdir": str(outdir / "megahit")},
            )
        else:
            chosen = "metaspades"
            step = StepSpec(
                step_id=f"asm.metaspades.{sample.sample_id}",
                tool_id="assembly.metaspades",
                kwargs={"in1": in1, "in2": in2, "outdir": str(outdir / "metaspades")},
            )
        return chosen, step

    def _bin_and_qc(
        self,
        sample: Sample,
        assembly: AssemblyResult,
        contigs_path: Path | None,
        ctx: AgentContext,
    ):
        """Run binning + MAG QC. v0.1 falls through to a "single MAG = entire
        assembly" placeholder when binners are unavailable, so BGC discovery
        is still exercised end-to-end."""
        artifacts = []
        rationales = []

        # --- attempt binning ------------------------------------------------
        bins_dir = ctx.workdir / "bins" / sample.sample_id
        bins_dir.mkdir(parents=True, exist_ok=True)
        bin_paths: list[Path] = []
        try:
            depths = bins_dir / "depths.tsv"  # would be produced by jgi_summarize_bam_contig_depths
            if not depths.is_file():
                raise ToolUnavailable("read-mapping depths not produced (jgi_summarize_bam_contig_depths missing)")
            res = ctx.runner.execute(
                StepSpec(
                    step_id=f"bin.metabat2.{sample.sample_id}",
                    tool_id="binning.metabat2",
                    kwargs={
                        "contigs": str(contigs_path),
                        "depths": str(depths),
                        "outdir": str(bins_dir / "metabat2"),
                    },
                ),
                ctx.tools,
            )
            bin_paths = list(res.output_paths)
        except ToolUnavailable as exc:
            rationales.append(
                ctx.make_rationale(
                    self.name,
                    f"Binning deferred for {sample.sample_id}: {exc}. "
                    "Treating assembly as a single placeholder MAG for downstream stages.",
                )
            )

        if not bin_paths and contigs_path is not None and Path(contigs_path).is_file():
            bin_paths = [Path(contigs_path)]

        if not bin_paths:
            return None, artifacts, rationales, None

        # v0.1 advances only the largest bin. Multi-bin handling is wired but
        # gated behind real binner availability.
        primary = max(bin_paths, key=lambda p: Path(p).stat().st_size if Path(p).is_file() else 0)
        mag_id = f"M_{short_hash(sample.sample_id, str(primary))}"

        is_fungal: bool | None = None
        try:
            res = ctx.runner.execute(
                StepSpec(
                    step_id=f"eukrep.{sample.sample_id}",
                    tool_id="domain.eukrep",
                    kwargs={
                        "contigs": str(primary),
                        "outdir": str(bins_dir / "eukrep"),
                    },
                ),
                ctx.tools,
            )
            # Heuristic: a MAG is fungal if EukRep retains > 50% of bp.
            euk_path = next((p for p in res.output_paths if "eukaryote" in str(p)), None)
            if euk_path and Path(euk_path).is_file():
                euk_len = fasta_assembly_stats(Path(euk_path))["total_length"]
                tot = fasta_assembly_stats(Path(primary))["total_length"] or 1
                is_fungal = euk_len / tot > 0.5
        except ToolUnavailable:
            pass

        completeness, contamination, busco_complete = None, None, None
        try:
            res = ctx.runner.execute(
                StepSpec(
                    step_id=f"checkm2.{sample.sample_id}",
                    tool_id="magqc.checkm2",
                    kwargs={"bins_dir": str(primary.parent), "outdir": str(bins_dir / "checkm2")},
                ),
                ctx.tools,
            )
            per_bin = res.metrics.get("per_bin", {})
            row = per_bin.get(primary.stem) or next(iter(per_bin.values()), {})
            completeness = row.get("completeness")
            contamination = row.get("contamination")
        except ToolUnavailable:
            pass

        try:
            res = ctx.runner.execute(
                StepSpec(
                    step_id=f"busco.{sample.sample_id}",
                    tool_id="magqc.busco",
                    kwargs={"fasta": str(primary), "outdir": str(bins_dir / "busco")},
                ),
                ctx.tools,
            )
            busco_complete = res.metrics.get("complete_pct")
        except ToolUnavailable:
            pass

        contigs_stats = (
            fasta_assembly_stats(Path(primary)) if Path(primary).is_file() else {}
        )
        mag = MAG(
            mag_id=mag_id,
            sample_id=sample.sample_id,
            binner="metabat2",
            fasta_artifact_id=assembly.assembly_artifact_id,
            completeness=completeness,
            contamination=contamination,
            n_contigs=contigs_stats.get("n_contigs"),
            total_length=contigs_stats.get("total_length"),
            busco_complete=busco_complete,
            busco_lineage="ascomycota_odb10" if busco_complete is not None else None,
            is_fungal=is_fungal,
        )
        rationales.append(
            ctx.make_rationale(
                self.name,
                claim=(
                    f"MAG {mag_id} from {sample.sample_id}: "
                    f"checkm2_complete={completeness}, contamination={contamination}, "
                    f"busco_ascomycota={busco_complete}, fungal={is_fungal}."
                ),
                evidence_artifact_ids=[assembly.assembly_artifact_id]
                if assembly.assembly_artifact_id.startswith("art_") and not assembly.assembly_artifact_id.startswith("art_assembly_")
                else [],
            )
        )

        taxonomy = (
            TaxonomyCall(
                mag_id=mag_id,
                domain="Eukaryota",
                phylum="Ascomycota" if (busco_complete or 0) > 50 else None,
                method="EukRep+BUSCO_ascomycota",
                confidence=(busco_complete / 100) if busco_complete is not None else None,
            )
            if is_fungal
            else None
        )
        return mag, artifacts, rationales, taxonomy
