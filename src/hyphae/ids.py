"""Short, deterministic-ish identifiers for runs, artifacts, rationales.

Hex-prefixed UUID4s when ``deterministic=False``, content-based hashes when
``deterministic=True``. The deterministic mode is what lets golden runs be
bit-reproducible.
"""

from __future__ import annotations

import hashlib
import uuid


def new_run_id(seed: str | None = None) -> str:
    if seed is not None:
        return "run_" + hashlib.sha256(seed.encode()).hexdigest()[:16]
    return "run_" + uuid.uuid4().hex[:16]


def new_artifact_id(sha256: str) -> str:
    return "art_" + sha256[:12]


def new_rationale_id(producer_agent: str, claim: str, deterministic: bool = False) -> str:
    if deterministic:
        h = hashlib.sha256(f"{producer_agent}::{claim}".encode()).hexdigest()
        return "rat_" + h[:12]
    return "rat_" + uuid.uuid4().hex[:12]


def short_hash(*parts: str) -> str:
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return h[:12]
