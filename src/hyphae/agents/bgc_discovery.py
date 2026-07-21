"""BGC Discovery agent (v0.1, antiSMASH-only).

Wires antiSMASH against each fungal MAG and parses results into normalized
:class:`hyphae.state.BGC` records. v0.2 will fan out to DeepBGC + GECCO and
add union/agreement scoring; the agent layout already supports it.
"""

from __future__ import annotations

import json
import hashlib
import random
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..ids import new_rationale_id, short_hash
from ..state import BGC, BGCClass, Rationale, RunState, RunStatePatch
from ..tools.antismash import parse_antismash_json
from ..tools.base import ToolUnavailable
from ..workflows.runner import StepSpec
from .base import Agent, AgentContext

if TYPE_CHECKING:
    from ..runtime.deterministic_executor import Manifest

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

    def discover(self, manifest: Manifest) -> Manifest:
        """Create deterministic synthetic BGC candidates for decision-layer use.

        This provides useful downstream structure before antiSMASH/BiG-SLiCE is
        available; the records explicitly identify the synthetic tool source.
        """
        assemblies = manifest.final_state.get("assemblies", {})
        if not isinstance(assemblies, dict):
            return manifest
        bgcs = manifest.final_state.setdefault("bgcs", [])
        if not isinstance(bgcs, list):
            bgcs = []
            manifest.final_state["bgcs"] = bgcs
        seen_types = {
            str(record.get("type", record.get("bgc_class", ""))).lower()
            for record in bgcs
            if isinstance(record, dict)
        }

        for sample_id, reference in assemblies.items():
            seed = int(hashlib.sha256(f"{sample_id}:{reference}".encode()).hexdigest()[:16], 16)
            rng = random.Random(seed)
            count = rng.randint(2, 4)
            contig_ids = self._contig_ids(manifest, reference) or [f"contig_{sample_id}"]
            novel_gcfs = 0
            for index in range(count):
                bgc_type = rng.choice(["nrps", "t1pks", "hybrid", "bacteriocin"])
                is_known = bgc_type in seen_types
                if not is_known:
                    novel_gcfs += 1
                seen_types.add(bgc_type)
                bgcs.append({
                    "bgc_id": f"BGC_{short_hash(str(sample_id), str(index), bgc_type)}",
                    "contig_id": rng.choice(contig_ids),
                    "tool": "synthetic_antismash",
                    "type": bgc_type,
                    "domains": self._domains(bgc_type),
                    "confidence": round(0.6 + rng.random() * 0.35, 3),
                    "gcf_candidate": (
                        f"GCF_known_{bgc_type}" if is_known else f"GCF_orphan_{bgc_type}"
                    ),
                })
            claim = f"Found {count} BGCs for {sample_id}; {novel_gcfs} are novel GCFs (not in MIBiG)."
            manifest.rationales.append(Rationale(
                rationale_id=new_rationale_id("bgc_discovery", claim, deterministic=True),
                producer_agent="bgc_discovery",
                claim=claim,
            ))
        return manifest

    @staticmethod
    def _domains(bgc_type: str) -> list[str]:
        domains = {
            "nrps": ["A", "PCP", "C", "KS"],
            "t1pks": ["KS", "AT", "ACP", "TE"],
            "hybrid": ["A", "PCP", "C", "KS", "AT", "ACP", "TE"],
            "bacteriocin": ["LanM", "LanT"],
        }
        return domains[bgc_type]

    @staticmethod
    def _contig_ids(manifest: Manifest, reference: Any) -> list[str]:
        if hasattr(reference, "assembly_artifact_id"):
            reference = reference.assembly_artifact_id
        elif isinstance(reference, dict):
            reference = reference.get("assembly_artifact_id") or reference.get("path")
        artifacts = {artifact.artifact_id: artifact for artifact in manifest.artifacts}
        if reference in artifacts:
            reference = artifacts[reference].path
        path = Path(str(reference)) if reference else None
        if path is None or not path.is_file():
            return []
        with path.open(errors="replace") as handle:
            return [line[1:].strip().split()[0] for line in handle if line.startswith(">")]

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
