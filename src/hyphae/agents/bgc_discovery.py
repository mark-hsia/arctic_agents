"""BGC Discovery agent (v0.1, antiSMASH-only).

Wires antiSMASH against each fungal MAG and parses results into normalized
:class:`hyphae.state.BGC` records. v0.2 will fan out to DeepBGC + GECCO and
add union/agreement scoring; the agent layout already supports it.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..ids import new_rationale_id, short_hash
from ..state import BGC, BGCClass, Rationale, RunState, RunStatePatch
from ..tools.antismash import parse_antismash_json
from ..tools.base import ToolUnavailable
from ..workflows.runner import StepSpec
from .base import Agent, AgentContext
from ..guard import validate_output

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

    def __init__(self, max_wait_seconds: int = 7200, poll_interval_seconds: int = 30) -> None:
        """Configure queue waiting for asynchronous antiSMASH submissions."""
        self.antismash_url = "https://antismash.secondarymetabolites.org/api/v1"
        self.max_retries = 3
        self.max_wait_seconds = max_wait_seconds
        self.poll_interval_seconds = poll_interval_seconds

    def discover(
        self, manifest: Manifest | dict[str, Any], max_wait_seconds: int | None = None
    ) -> Manifest | Any:
        """Discover BGCs using the local/API/HMMER production cascade."""
        if not hasattr(manifest, "final_state"):
            manifest = self._dict_to_obj(manifest)
        assemblies = manifest.final_state.get("assemblies", {})
        bgcs: list[dict[str, Any]] = []
        for assembly_id, assembly_path in assemblies.items() if isinstance(assemblies, dict) else []:
            logger.info("Detecting secondary-metabolite domains in %s", assembly_id)
            bgcs.extend(self._run_antismash(str(assembly_path), str(assembly_id)))
        if not bgcs:
            raise RuntimeError(
                "No secondary-metabolite domains were detected. Verify contigs or install antiSMASH, or install "
                "Prodigal + HMMER and set HYPHAE_PFAM_HMM to a pressed Pfam-A HMM database."
            )
        manifest.final_state["bgcs"] = bgcs
        claim = f"Detected {len(bgcs)} BGC candidates via antiSMASH/HMMER domain analysis"
        self._append_manifest_rationale(
            manifest, claim, list(assemblies) if isinstance(assemblies, dict) else []
        )
        return manifest

    def _run_antismash(self, contig_fasta: str, assembly_id: str) -> list[dict[str, Any]]:
        """Try local antiSMASH, queued API, then local Prodigal/HMMER/Pfam."""
        path = Path(contig_fasta)
        if not path.is_file():
            raise FileNotFoundError(f"Contig file {contig_fasta} not found")
        failures: list[str] = []
        try:
            return self._run_antismash_local(str(path), assembly_id)
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as exc:
            failures.append(f"local antiSMASH: {exc}")
            logger.info("Local antiSMASH unavailable for %s: %s", assembly_id, exc)
        try:
            return self._run_antismash_api(str(path), assembly_id)
        except Exception as exc:
            failures.append(f"antiSMASH API: {exc}")
            logger.warning("antiSMASH API unavailable for %s: %s", assembly_id, exc)
        try:
            return self._hmmer_detection(path, assembly_id)
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as exc:
            failures.append(f"HMMER: {exc}")
        raise RuntimeError(
            "No BGC detection tool succeeded. Install antiSMASH (`conda install -c bioconda antismash`) "
            "or Prodigal/HMMER (`conda install -c bioconda prodigal hmmer`) and configure "
            "HYPHAE_PFAM_HMM. Details: " + "; ".join(failures)
        )

    def _hmmer_detection(self, contig_path: Path, assembly_id: str) -> list[dict[str, Any]]:
        """Predict proteins with Prodigal, call Pfam with HMMER, and form real hit regions."""
        pfam_hmm = Path(os.environ.get("HYPHAE_PFAM_HMM", ""))
        if not pfam_hmm.is_file():
            raise FileNotFoundError("HYPHAE_PFAM_HMM must point to a pressed Pfam-A HMM file")
        genes_faa = contig_path.with_name(f"{contig_path.stem}_genes.faa")
        genes_gff = contig_path.with_name(f"{contig_path.stem}_genes.gff")
        domtblout = contig_path.with_name(f"{contig_path.stem}_pfam.domtblout")
        subprocess.run(
            ["prodigal", "-i", str(contig_path), "-a", str(genes_faa), "-o", str(genes_gff), "-f", "gff", "-p", "meta"],
            check=True, capture_output=True, text=True, timeout=300,
        )
        subprocess.run(
            ["hmmscan", "--domtblout", str(domtblout), "--noali", str(pfam_hmm), str(genes_faa)],
            check=True, capture_output=True, text=True, timeout=1800,
        )
        return self._parse_hmmer_output(domtblout, genes_gff, assembly_id)

    @staticmethod
    def _parse_hmmer_output(domtblout: Path, genes_gff: Path, assembly_id: str) -> list[dict[str, Any]]:
        """Convert Pfam domain-table hits into coordinate-backed BGC candidates."""
        domain_types = {
            "PF00501": "NRPS", "PF00668": "NRPS", "PF00550": "NRPS",
            "PF00109": "PKS", "PF02801": "PKS", "PF00023": "PKS",
            "PF03936": "Terpene", "PF13243": "Terpene",
        }
        gene_locations: dict[str, tuple[str, int, int]] = {}
        with genes_gff.open(errors="replace") as handle:
            for line in handle:
                if line.startswith("#"):
                    continue
                fields = line.rstrip().split("\t")
                if len(fields) != 9 or fields[2] != "CDS":
                    continue
                attributes = dict(
                    item.split("=", 1) for item in fields[8].split(";") if "=" in item
                )
                gene_id = attributes.get("ID")
                if gene_id:
                    gene_locations[gene_id] = (fields[0], int(fields[3]), int(fields[4]))
        hits: dict[str, list[str]] = {}
        with domtblout.open(errors="replace") as handle:
            for line in handle:
                if not line.strip() or line.startswith("#"):
                    continue
                fields = line.split()
                if len(fields) < 4:
                    continue
                pfam_id = fields[0].split(".")[0]
                gene_id = fields[3]
                if pfam_id in domain_types and gene_id in gene_locations:
                    hits.setdefault(gene_id, []).append(pfam_id)
        by_contig: dict[str, list[tuple[int, int, str, str]]] = {}
        for gene_id, domains in hits.items():
            contig, start, end = gene_locations[gene_id]
            for domain in sorted(set(domains)):
                by_contig.setdefault(contig, []).append((start, end, domain, domain_types[domain]))
        bgcs: list[dict[str, Any]] = []
        for index, (contig, entries) in enumerate(sorted(by_contig.items())):
            entries.sort()
            domains = sorted({entry[2] for entry in entries})
            types = sorted({entry[3] for entry in entries})
            bgc_type = "Hybrid" if "NRPS" in types and "PKS" in types else types[0]
            bgcs.append({
                "bgc_id": f"{assembly_id}_{contig}_bgc_{index}",
                "assembly_id": assembly_id,
                "type": bgc_type.lower(),
                "product_types": types,
                "domains": domains,
                "contig_id": contig,
                "start": min(entry[0] for entry in entries),
                "end": max(entry[1] for entry in entries),
                "confidence": min(0.95, 0.6 + 0.05 * len(domains)),
                "tool": "hmmer",
                "source": "hmmer_pfam",
            })
        return bgcs

    def _run_antismash_local(self, contig_fasta: str, assembly_id: str) -> list[dict[str, Any]]:
        """Run a locally installed antiSMASH binary and parse its JSON result."""
        output_dir = Path(f"antismash_output_{assembly_id}")
        output_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            "antismash",
            "--minlength", "1000",
            "--genefinder", "prodigal",
            "--output-dir", str(output_dir),
            "--output-format", "json",
            contig_fasta,
        ]
        logger.info("Running local antiSMASH for %s", assembly_id)
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=3600)
        json_file = output_dir / "results.json"
        if not json_file.is_file():
            json_file = next(output_dir.glob("*.json"), None)
        if json_file is None or not json_file.is_file():
            raise RuntimeError(f"Local antiSMASH completed without a JSON result in {output_dir}")
        return self._parse_antismash_result(json.loads(json_file.read_text()), assembly_id)

    def _run_antismash_api(self, contig_fasta: str, assembly_id: str) -> list[dict[str, Any]]:
        """Submit to the public API with automatic retry and queue polling."""
        path = Path(contig_fasta)
        try:
            import requests
        except ImportError as exc:
            raise RuntimeError("requests is required for antiSMASH API access") from exc
        fasta_content = path.read_text()
        failures: list[str] = []
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(
                    f"{self.antismash_url}/submit",
                    files={"sequence": (path.name, fasta_content, "text/plain")},
                    data={"email": "hyphae@example.com", "ncbi": "off"},
                    timeout=30,
                )
                if response.status_code != 200:
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")
                job_id = response.json().get("submission_id")
                if not job_id:
                    raise RuntimeError("no submission_id returned")
                result = self._poll_antismash(
                    job_id, assembly_id, self.max_wait_seconds, self.poll_interval_seconds
                )
                if result is not None:
                    return self._parse_antismash_result(result, assembly_id)
                failures.append(f"attempt {attempt}: job {job_id} did not complete")
            except Exception as exc:
                failures.append(f"attempt {attempt}: {exc}")
            if attempt < self.max_retries:
                time.sleep(min(self.poll_interval_seconds, 30))
        raise RuntimeError("antiSMASH API unavailable after retries: " + "; ".join(failures))

    def _poll_antismash(
        self,
        job_id: str,
        assembly_id: str,
        timeout_sec: int = 7200,
        poll_interval: int = 30,
    ) -> dict[str, Any] | None:
        """Poll queued/running jobs until complete, timeout, or terminal failure."""
        try:
            import requests
        except ImportError as exc:
            raise RuntimeError("requests is required for antiSMASH API access") from exc
        started = time.monotonic()
        poll_count = 0
        last_status: str | None = None
        while time.monotonic() - started < timeout_sec:
            elapsed = int(time.monotonic() - started)
            try:
                response = requests.get(f"{self.antismash_url}/results/{job_id}", timeout=10)
                if response.status_code == 404:
                    if last_status != "queued":
                        logger.info("antiSMASH job %s (%s): queued", job_id, assembly_id)
                        last_status = "queued"
                    elif poll_count % 10 == 0:
                        logger.info("antiSMASH job %s: still queued after %ss", job_id, elapsed)
                    poll_count += 1
                    time.sleep(poll_interval)
                    continue
                if response.status_code != 200:
                    logger.warning("antiSMASH job %s: HTTP %s; retrying", job_id, response.status_code)
                    time.sleep(poll_interval)
                    continue
                result = response.json()
                status = str(result.get("status", "unknown"))
                if status == "done":
                    logger.info("antiSMASH job %s completed after %ss", job_id, elapsed)
                    return result
                if status == "failed":
                    logger.error("antiSMASH job %s failed: %s", job_id, result.get("error", "unknown"))
                    return None
                if status != last_status:
                    logger.info("antiSMASH job %s (%s): %s", job_id, assembly_id, status)
                    last_status = status
                elif poll_count % 10 == 0:
                    logger.info("antiSMASH job %s: %s after %ss", job_id, status, elapsed)
                poll_count += 1
            except requests.exceptions.Timeout:
                logger.warning("antiSMASH job %s: request timeout; retrying", job_id)
            except requests.exceptions.ConnectionError as exc:
                logger.warning("antiSMASH job %s: connection error; retrying: %s", job_id, exc)
            except Exception as exc:
                logger.warning("antiSMASH job %s: unexpected poll error; retrying: %s", job_id, exc)
            time.sleep(poll_interval)
        logger.error("antiSMASH job %s timed out after %ss", job_id, timeout_sec)
        return None

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

    @validate_output
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
                rationale = ctx.make_rationale(
                        self.name,
                        f"antiSMASH deferred for MAG {mag.mag_id}: "
                        f"FASTA artifact {mag.fasta_artifact_id!r} is not in run state.",
                    )
                rationale.accepted = False
                new_rationales.append(rationale)
                continue

            fasta_path = ctx.artifact_store.resolve(fasta_artifact)
            if not fasta_path.is_file():
                rationale = ctx.make_rationale(
                        self.name,
                        f"antiSMASH deferred for MAG {mag.mag_id}: "
                        f"FASTA artifact {mag.fasta_artifact_id!r} is missing from the artifact store.",
                        evidence_artifact_ids=[fasta_artifact.artifact_id],
                    )
                rationale.accepted = False
                new_rationales.append(rationale)
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
                rationale = ctx.make_rationale(
                        self.name,
                        f"antiSMASH failed for MAG {mag.mag_id}: {exc}.",
                        evidence_artifact_ids=[fasta_artifact.artifact_id],
                    )
                rationale.accepted = False
                new_rationales.append(rationale)
                continue

            json_path = next(
                (p for p in result.output_paths if str(p).endswith(".json")),
                None,
            )
            cluster_dicts: list[dict] = []
            evidence_ids: list[str] = []
            if json_path is not None and Path(json_path).is_file():
                try:
                    cluster_dicts = parse_antismash_json(Path(json_path))
                    report_artifact = ctx.artifact_store.put_path(
                        Path(json_path), producer_agent=self.name, run_id=ctx.run_id,
                        tool_version=result.tool_version, mime_type="application/json",
                        parent_ids=[fasta_artifact.artifact_id],
                    )
                    new_artifacts.append(report_artifact)
                    evidence_ids = [report_artifact.artifact_id]
                except (ValueError, json.JSONDecodeError):
                    cluster_dicts = []
            if not evidence_ids:
                rationale = ctx.make_rationale(
                    self.name, f"antiSMASH result for MAG {mag.mag_id} deferred: no parseable JSON evidence artifact was produced.",
                    [fasta_artifact.artifact_id],
                )
                rationale.accepted = False
                new_rationales.append(rationale)
                continue

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
                    evidence_artifact_ids=evidence_ids,
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
