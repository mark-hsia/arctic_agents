"""antiSMASH wrappers — local binary and hosted web API client.

The web client is hosted-first per the platform charter. It is a thin client
against the antiSMASH job submission API (https://antismash.secondarymetabolites.org/).
Without a real API key / endpoint it reports unavailable, so the registry
falls through to the local binary, then to the replay path.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .base import Tool, ToolRunResult, ToolUnavailable, run_shell


class LocalAntiSmash(Tool):
    tool_id = "bgc.antismash"
    binary = "antismash"

    def run(self, **kwargs: Any) -> ToolRunResult:
        if not self.is_available():
            raise ToolUnavailable("antismash not on PATH")
        fasta: Path = Path(kwargs["fasta"])
        outdir: Path = Path(kwargs["outdir"])
        taxon: str = kwargs.get("taxon", "fungi")
        threads: int = int(kwargs.get("threads", 4))
        outdir.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.binary,  # type: ignore[list-item]
            str(fasta),
            "--output-dir", str(outdir),
            "--taxon", taxon,
            "--genefinding-tool", "prodigal-m",
            "--cpus", str(threads),
            "--cb-general",
            "--cb-knownclusters",
            "--cb-subclusters",
            "--asf",
        ]
        t0 = time.time()
        run_shell(cmd)
        json_out = next(outdir.glob("*.json"), None)
        gbks = sorted(outdir.glob("*.region*.gbk"))
        n_clusters = len(gbks)
        return ToolRunResult(
            tool_id=self.tool_id,
            output_paths=([json_out] if json_out else []) + gbks,
            metrics={"n_clusters": n_clusters, "taxon": taxon},
            duration_seconds=time.time() - t0,
        )


class AntiSmashWebClient(Tool):
    """Hosted antiSMASH job submission client.

    Available when ``HYPHAE_ANTISMASH_URL`` is set. Real implementation
    submits a job, polls for completion, and downloads the result archive.
    The poll/download logic is intentionally minimal here; the network shape
    is what matters for the platform contract.
    """

    tool_id = "bgc.antismash"

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = base_url or os.environ.get("HYPHAE_ANTISMASH_URL")
        self.api_key = api_key or os.environ.get("HYPHAE_ANTISMASH_KEY")

    def is_available(self) -> bool:
        return bool(self.base_url)

    def run(self, **kwargs: Any) -> ToolRunResult:  # pragma: no cover - network
        if not self.is_available():
            raise ToolUnavailable("Hosted antiSMASH endpoint not configured")
        raise ToolUnavailable(
            "Hosted antiSMASH client not yet implemented; use local antismash binary"
        )


def parse_antismash_json(path: Path) -> list[dict[str, Any]]:
    """Parse antiSMASH ``*.json`` output into a normalized list of cluster dicts.

    We support both v6 and v7 output shapes. For each region we emit::

        {
            "contig": str,
            "start": int,
            "end": int,
            "type": str,
            "product": str | None,
            "tools": ["antismash"],
            "edge_truncated": bool,
        }
    """

    data = json.loads(Path(path).read_text())
    out: list[dict[str, Any]] = []
    records = data.get("records") or []
    for record in records:
        contig = record.get("id") or record.get("name") or ""
        seq_len = record.get("length") or 0
        for feature in record.get("features", []):
            ftype = feature.get("type") or ""
            if ftype not in {"region", "protocluster"}:
                continue
            qualifiers = feature.get("qualifiers", {}) or {}
            location = feature.get("location", "")
            try:
                start, end = _parse_location(location)
            except ValueError:
                continue
            products = qualifiers.get("product") or qualifiers.get("category") or []
            if isinstance(products, list) and products:
                product = "/".join(products)
            else:
                product = products if isinstance(products, str) else None
            edge = (start <= 1) or (seq_len and end >= seq_len - 1)
            out.append(
                {
                    "contig": contig,
                    "start": int(start),
                    "end": int(end),
                    "type": ftype,
                    "product": product,
                    "tools": ["antismash"],
                    "edge_truncated": bool(edge),
                }
            )
    return out


def _parse_location(loc: str) -> tuple[int, int]:
    """Parse a Biopython-style location string ``[123:456](+)``."""
    body = loc.strip().lstrip("[").split("]")[0]
    if ":" not in body:
        raise ValueError(loc)
    a, b = body.split(":", 1)
    return int(a), int(b)
