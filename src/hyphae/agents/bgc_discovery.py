"""BGC Discovery agent (v0.1, antiSMASH-only).

Wires antiSMASH against each fungal MAG and parses results into normalized
:class:`hyphae.state.BGC` records. v0.2 will fan out to DeepBGC + GECCO and
add union/agreement scoring; the agent layout already supports it.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..ids import new_rationale_id, short_hash
from ..state import BGC, BGCClass, Rationale, RunState, RunStatePatch
from ..tools.antismash import parse_antismash_json
from ..tools.base import ToolUnavailable
from ..workflows.runner import StepSpec
from .base import Agent, AgentContext

if TYPE_CHECKING:
    from ..manifest import Manifest

logger = logging.getLogger(__name__)

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
    """Discover real BGCs by submitting assembled contigs to antiSMASH."""

    name = "bgc_discovery"
    reads = ("mags", "taxonomy")
    writes = ("bgcs",)
    tools = ("bgc.antismash",)

    def __init__(self) -> None:
        self.antismash_url = "https://antismash.secondarymetabolites.org/api/v1"
        self.max_retries = 3

    def discover(self, manifest: Manifest | dict[str, Any]) -> Manifest | Any:
        """Populate ``bgcs`` only from completed antiSMASH API results."""
        if not hasattr(manifest, "final_state"):
            manifest = self._dict_to_obj(manifest)
        assemblies = manifest.final_state.get("assemblies", {})
        bgcs: list[dict[str, Any]] = []
        for assembly_id, assembly_path in assemblies.items() if isinstance(assemblies, dict) else []:
            try:
                bgcs.extend(self._run_antismash(str(assembly_path), str(assembly_id)))
            except Exception as exc:
                logger.warning("antiSMASH failed for %s: %s", assembly_id, exc)
        manifest.final_state["bgcs"] = bgcs
        claim = f"Found {len(bgcs)} BGCs via antiSMASH API"
        self._append_manifest_rationale(
            manifest, claim, list(assemblies) if isinstance(assemblies, dict) else []
        )
        return manifest

    def _run_antismash(self, contig_fasta: str, assembly_id: str) -> list[dict[str, Any]]:
        path = Path(contig_fasta)
        if not path.is_file():
            raise FileNotFoundError(f"Contig file {contig_fasta} not found")
        try:
            import requests

            response = requests.post(
                f"{self.antismash_url}/submit",
                files={"sequence": (path.name, path.read_text(), "text/plain")},
                data={"email": "hyphae@example.com", "ncbi": "off"},
                timeout=30,
            )
            if response.status_code != 200:
                raise RuntimeError(f"antiSMASH submit failed ({response.status_code}): {response.text[:500]}")
            job_id = response.json().get("submission_id")
            if not job_id:
                raise RuntimeError("antiSMASH did not return a submission_id")
            return self._poll_antismash(job_id, assembly_id)
        except Exception as exc:
            raise RuntimeError(f"antiSMASH API unavailable: {exc}") from exc

    def _poll_antismash(self, job_id: str, assembly_id: str, max_wait_sec: int = 300) -> list[dict[str, Any]]:
        try:
            import requests
        except ImportError as exc:
            raise RuntimeError("requests is required for antiSMASH API access") from exc
        started = time.monotonic()
        while time.monotonic() - started < max_wait_sec:
            try:
                response = requests.get(f"{self.antismash_url}/results/{job_id}", timeout=10)
                if response.status_code == 404:
                    time.sleep(5)
                    continue
                if response.status_code != 200:
                    time.sleep(5)
                    continue
                result = response.json()
                if result.get("status") == "done":
                    return self._parse_antismash_result(result, assembly_id)
                if result.get("status") == "failed":
                    raise RuntimeError(str(result.get("error", "antiSMASH job failed")))
            except Exception as exc:
                logger.debug("antiSMASH poll error for %s: %s", job_id, exc)
            time.sleep(5)
        raise RuntimeError(f"antiSMASH job {job_id} timed out")

    @staticmethod
    def _parse_antismash_result(result: dict[str, Any], assembly_id: str) -> list[dict[str, Any]]:
        bgcs: list[dict[str, Any]] = []
        for record_index, record in enumerate(result.get("records", [])):
            for cluster_index, cluster in enumerate(record.get("clusters", [])):
                products = cluster.get("product", [])
                products = [products] if isinstance(products, str) else list(products or [])
                domains = list(dict.fromkeys(
                    str(motif.get("note", ""))
                    for motif in cluster.get("cds_motifs", [])
                    if isinstance(motif, dict) and motif.get("note")
                ))
                raw_confidence = cluster.get("detection_rule", {}).get("confidence", 0.7)
                confidence = 0.9 if raw_confidence == "high" else 0.7 if isinstance(raw_confidence, str) else float(raw_confidence)
                bgcs.append({
                    "bgc_id": f"{assembly_id}_cluster_{record_index}_{cluster_index}",
                    "assembly_id": assembly_id,
                    "type": products[0] if products else "unknown",
                    "product_types": products,
                    "domains": domains,
                    "contig_id": record.get("id", f"contig_{record_index}"),
                    "start": cluster.get("start"),
                    "end": cluster.get("end"),
                    "confidence": confidence,
                    "tool": "antismash",
                    "gcf_candidate": None,
                    "source": "antismash_api",
                })
        return bgcs

    @staticmethod
    def _dict_to_obj(data: dict[str, Any]) -> Any:
        class Obj:
            def __init__(self, values: dict[str, Any]) -> None:
                self.__dict__.update(values)
                self.final_state = getattr(self, "final_state", {})
                self.rationales = getattr(self, "rationales", [])
        return Obj(data)

    @staticmethod
    def _append_manifest_rationale(manifest: Any, claim: str, artifact_ids: list[str]) -> None:
        try:
            from ..manifest import Rationale as ManifestRationale

            manifest.rationales.append(ManifestRationale(
                rationale_id=f"rat_bgc_{len(manifest.rationales)}",
                producer_agent="bgc_discovery",
                claim=claim,
                evidence_artifact_ids=artifact_ids,
            ))
        except ImportError:
            manifest.rationales.append(Rationale(
                rationale_id=new_rationale_id("bgc_discovery", claim, deterministic=True),
                producer_agent="bgc_discovery",
                claim=claim,
                evidence_artifact_ids=artifact_ids,
            ))

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
