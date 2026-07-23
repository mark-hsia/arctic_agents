"""Safeguard: reject fabricated data from typed agent patches."""

from __future__ import annotations

import logging
from functools import wraps

from .state import RunStatePatch

logger = logging.getLogger("hyphae.safeguard")
SYNTHETIC_MARKERS = {"stub", "fake", "synthetic", "placeholder", "mock", "hardcoded", "[stub_", "[fake_", "test_only", "fallback"}


def forbid_synthetic_data(func):
    """Reject synthetic markers in accepted claims and emitted artifacts/results."""
    @wraps(func)
    def wrapper(self, state, ctx):
        patch = func(self, state, ctx)
        _check_patch_for_synthetic(patch, agent_name=self.name)
        return patch
    return wrapper


def _check_patch_for_synthetic(patch: RunStatePatch, agent_name: str) -> None:
    data = patch.model_dump(exclude_none=True)
    for rationale in data.get("rationales", []):
        if not rationale.get("accepted", True):
            continue
        _reject_markers(str(rationale.get("claim", "")), agent_name, "claim")
    for artifact in data.get("artifacts", []):
        _reject_markers(str(artifact.get("path", "")), agent_name, "artifact path")
    for structures in data.get("structures", {}).values():
        for structure in structures:
            if structure.get("smiles") in {"C", "CC", "CCC", "[PLACEHOLDER]"}:
                raise ValueError(f"Agent '{agent_name}' produced placeholder SMILES")
    for results in data.get("docking", {}).values():
        for result in results:
            if result.get("method") not in {"vina", "diffdock"}:
                raise ValueError(f"Agent '{agent_name}' produced non-empirical docking method")
    logger.info("Agent '%s' output passed no-synthetic-data check", agent_name)


def _reject_markers(value: str, agent_name: str, field: str) -> None:
    lowered = value.lower()
    if any(marker in lowered for marker in SYNTHETIC_MARKERS):
        raise ValueError(f"Agent '{agent_name}' produced {field} containing a synthetic-data marker")


def allow_deferred_only(func):
    """Ensure an empty result is accompanied by a rejected deferral rationale."""
    @wraps(func)
    def wrapper(self, state, ctx):
        patch = func(self, state, ctx)
        data = patch.model_dump(exclude_none=True)
        real = any(data.get(key) for key in ("samples", "assemblies", "mags", "bgcs", "structures", "docking"))
        deferred = any(not rationale.get("accepted", True) for rationale in data.get("rationales", []))
        if not real and not deferred:
            raise ValueError(f"Agent '{self.name}' produced neither real output nor deferred rationale")
        return patch
    return wrapper
