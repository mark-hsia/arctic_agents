"""BGC Discovery agent (v0.1, antiSMASH-only).

Wires antiSMASH against each fungal MAG and parses results into normalized
:class:`hyphae.state.BGC` records. v0.2 will fan out to DeepBGC + GECCO and
add union/agreement scoring; the agent layout already supports it.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..ids import short_hash
from ..state import BGC, BGCClass, RunState, RunStatePatch
from ..tools.antismash import parse_antismash_json
from ..tools.base import ToolUnavailable
from ..workflows.runner import StepSpec
from .base import Agent, AgentContext

_CLASS_NORMALIZE = {
    "T1PKS": BGCClass.t1pks,
    "T2PKS": BGCClass.t2pks,
    "T3PKS": BGCClass.t3pks,
    "NRPS": BGCClass.nrps,
    "NRPS-like": BGCClass.nrps_like,
    "NRPS_like": BGCClass.nrps_like,
    "hglE-KS": BGCClass.t1pks,
    "transAT-PKS": BGCClass.t1pks,
    "PKS-NRPS": BGCClass.pks_nrps_hybrid,
    "NRPS-PKS": BGCClass.pks_nrps_hybrid,
    "terpene": BGCClass.terpene,
    "RiPP": BGCClass.ripp,
    "fungal-RiPP-like": BGCClass.fungal_ripp_like,
    "fungal-RiPP": BGCClass.fungal_ripp_like,
    "indole": BGCClass.indole,
    "siderophore": BGCClass.siderophore,
}


def normalize_class(raw: str | None) -> BGCClass:
    if not raw:
        return BGCClass.other
    for key, val in _CLASS_NORMALIZE.items():
        if key.lower() in raw.lower():
            return val
    return BGCClass.other


class BGCDiscoveryAgent(Agent):
    name = "bgc_discovery"
    reads = ("mags", "taxonomy")
    writes = ("bgcs",)
    tools = ("bgc.antismash",)

    def step(self, state: RunState, ctx: AgentContext) -> RunStatePatch:
        new_bgcs: list[BGC] = []
        new_artifacts = []
        new_rationales = []
        artifacts_by_id = {artifact.artifact_id: artifact for artifact in state.artifacts}

        for mag in state.mags:
            if mag.is_fungal is False:
                continue  # explicitly non-fungal — skip in v0.1 antifungal scope

            fasta_artifact = artifacts_by_id.get(mag.fasta_artifact_id)
            if fasta_artifact is None:
                new_rationales.append(
                    ctx.make_rationale(
                        self.name,
                        f"antiSMASH deferred for MAG {mag.mag_id}: "
                        f"FASTA artifact {mag.fasta_artifact_id!r} is not in run state.",
                    )
                )
                continue

            fasta_path = ctx.artifact_store.resolve(fasta_artifact)
            if not fasta_path.is_file():
                new_rationales.append(
                    ctx.make_rationale(
                        self.name,
                        f"antiSMASH deferred for MAG {mag.mag_id}: "
                        f"FASTA artifact {mag.fasta_artifact_id!r} is missing from the artifact store.",
                        evidence_artifact_ids=[fasta_artifact.artifact_id],
                    )
                )
                continue

            mag_workdir = ctx.workdir / "bgc" / mag.mag_id
            mag_workdir.mkdir(parents=True, exist_ok=True)
            step = StepSpec(
                step_id=f"antismash.{mag.mag_id}",
                tool_id="bgc.antismash",
                kwargs={
                    "fasta": str(fasta_path),
                    "outdir": str(mag_workdir / "antismash"),
                    "taxon": "fungi",
                },
            )

            try:
                result = ctx.runner.execute(step, ctx.tools)
            except (ToolUnavailable, RuntimeError, KeyError) as exc:
                new_rationales.append(
                    ctx.make_rationale(
                        self.name,
                        f"antiSMASH failed for MAG {mag.mag_id}: {exc}.",
                    )
                )
                continue

            json_path = next(
                (p for p in result.output_paths if str(p).endswith(".json")),
                None,
            )
            cluster_dicts: list[dict] = []
            if json_path is not None and Path(json_path).is_file():
                try:
                    cluster_dicts = parse_antismash_json(Path(json_path))
                except (ValueError, json.JSONDecodeError):
                    cluster_dicts = []
            elif result.metrics.get("clusters"):
                cluster_dicts = list(result.metrics["clusters"])

            for cd in cluster_dicts:
                bgc_id = f"BGC_{short_hash(mag.mag_id, cd['contig'], str(cd['start']))}"
                cls = normalize_class(cd.get("product") or cd.get("type"))
                new_bgcs.append(
                    BGC(
                        bgc_id=bgc_id,
                        mag_id=mag.mag_id,
                        contig=cd["contig"],
                        start=int(cd["start"]),
                        end=int(cd["end"]),
                        bgc_class=cls,
                        product=cd.get("product"),
                        domains=list(cd.get("domains", [])),
                        tools=list(cd.get("tools", ["antismash"])),
                        confidence=cd.get("confidence"),
                        edge_truncated=bool(cd.get("edge_truncated", False)),
                    )
                )

            new_rationales.append(
                ctx.make_rationale(
                    self.name,
                    claim=(
                        f"antiSMASH on MAG {mag.mag_id}: "
                        f"{len(cluster_dicts)} BGCs detected."
                    ),
                )
            )

        ctx.record(artifacts=new_artifacts, rationales=new_rationales)
        patch = RunStatePatch(
            bgcs=new_bgcs or None,
            artifacts=new_artifacts or None,
            rationales=new_rationales or None,
        )
        self.validate_patch(patch)
        return patch
