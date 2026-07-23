"""Deterministic guardrail for planner output and specialist failures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .planner import PlanStep
from ..state import RunState, RunStatePatch
from .base import Agent, AgentContext
from ..guard import validate_output

if TYPE_CHECKING:
    from ..runtime.deterministic_executor import Manifest


@dataclass(frozen=True)
class PlanReview:
    accepted: bool
    steps: list[PlanStep]
    comments: list[str]


class CriticAgent(Agent):
    """Reject plans that are unsafe, incomplete, or not dependency ordered."""

    REQUIRED_ORDER = ("ingestion", "assembly", "taxonomy", "bgc_discovery")
    name = "critic"
    reads = ("rationales", "artifacts", "structures", "docking", "literature", "novelty")
    writes = ()
    tools = ()

    @validate_output
    def step(self, state: RunState, ctx: AgentContext) -> RunStatePatch:
        """Append auditable critiques; append-only state cannot mutate prior claims."""
        known = {artifact.artifact_id for artifact in state.artifacts}
        critiques = []
        for rationale in state.rationales:
            missing = [artifact_id for artifact_id in rationale.evidence_artifact_ids if artifact_id not in known]
            if missing:
                critique = ctx.make_rationale(self.name, f"Rejected rationale {rationale.rationale_id}: missing evidence artifacts {', '.join(missing)}.")
                critique.accepted = False
                critiques.append(critique)
            elif not rationale.evidence_artifact_ids and rationale.accepted:
                critique = ctx.make_rationale(self.name, f"Rejected rationale {rationale.rationale_id}: accepted claim has no artifact provenance.")
                critique.accepted = False
                critiques.append(critique)
        ctx.record(rationales=critiques)
        patch = RunStatePatch(rationales=critiques or None)
        self.validate_patch(patch)
        return patch

    def review(self, manifest: Manifest) -> Manifest:
        """Validate manifest claims and retain an auditable rejection reason."""
        rejections: dict[str, int] = {}
        structures = self._records(manifest.final_state.get("structures", []))
        docking = self._records(manifest.final_state.get("docking", []))
        max_novelty = max(
            (float(record.get("novelty_score", 0.0)) for record in self._records(manifest.final_state.get("bgcs", []))),
            default=0.0,
        )
        for rationale in manifest.rationales:
            comments: list[str] = []
            artifact_ids = list(getattr(rationale, "evidence_artifact_ids", []))
            rationale_ids = list(getattr(rationale, "evidence_rationale_ids", []))
            if not artifact_ids:
                comments.append("Missing evidence")
            if not rationale_ids:
                comments.append("Dangling claim")
            related_structures = [
                record for record in structures if record.get("rationale_id") == rationale.rationale_id
            ]
            if max_novelty > 0.8 and related_structures and min(
                float(record.get("confidence", 0.0)) for record in related_structures
            ) < 0.5:
                comments.append("Novelty claim contradicted by weak inference")
            related_docking = [
                record for record in docking if record.get("rationale_id") == rationale.rationale_id
            ]
            if any(int(record.get("rank", 999999)) == 1 and self._pains(record, structures) for record in related_docking):
                comments.append("Docking rank driven by rule violation")
            confidence = self._confidence(rationale, related_structures, related_docking)
            evidence_sources = set(artifact_ids + rationale_ids)
            if confidence > 0.9 and len(evidence_sources) < 2:
                comments.append("High-confidence claim lacks two independent evidence sources")
            elif confidence < 0.5:
                comments.append("Exploratory: low-confidence claim")

            if comments:
                rationale.accepted = False
                rationale.critic_comments.extend(comment for comment in comments if comment not in rationale.critic_comments)
                for artifact_id in artifact_ids or ["global"]:
                    rejections[artifact_id] = rejections.get(artifact_id, 0) + 1
        escalations = manifest.final_state.setdefault("coordinator_escalations", [])
        for artifact_id, count in rejections.items():
            if count >= 3:
                escalations.append({"artifact_id": artifact_id, "rejections": count, "action": "review"})
        return manifest

    @staticmethod
    def _records(records: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for record in records if isinstance(records, list) else []:
            if hasattr(record, "model_dump"):
                record = record.model_dump()
            if isinstance(record, dict):
                out.append(record)
        return out

    @staticmethod
    def _confidence(rationale: Any, structures: list[dict[str, Any]], docking: list[dict[str, Any]]) -> float:
        if structures:
            return max(float(record.get("confidence", 0.0)) for record in structures)
        if docking:
            return max(0.0, min(1.0, (-min(float(record.get("vina_score", 0.0)) for record in docking)) / 10))
        return 0.5

    @staticmethod
    def _pains(docking: dict[str, Any], structures: list[dict[str, Any]]) -> bool:
        compound_id = docking.get("compound_id")
        smiles = next((str(record.get("smiles", "")) for record in structures if record.get("structure_id") == compound_id), "")
        return "pains" in smiles.lower() or (len(smiles) > 120 and "N" in smiles and "O" in smiles)

    def review_plan(self, plan: list[PlanStep], available_agents: set[str]) -> PlanReview:
        names = [step.agent_name for step in plan]
        if len(names) != len(set(names)):
            return PlanReview(False, [], ["plan contains duplicate agents"])
        if any(name not in available_agents for name in names):
            return PlanReview(False, [], ["plan contains an unavailable agent"])
        positions = [names.index(name) if name in names else -1 for name in self.REQUIRED_ORDER]
        if any(position < 0 for position in positions):
            return PlanReview(False, [], ["plan omits a required pipeline stage"])
        if positions != sorted(positions):
            return PlanReview(False, [], ["plan violates required data dependencies"])
        return PlanReview(True, plan, [])


def review_and_cite(manifest: Manifest, knowledge_cache: dict[str, Any]) -> Manifest:
    """Run manifest validation before attaching cache-backed citations."""
    from .literature import LiteratureAgent

    manifest = CriticAgent().review(manifest)
    return LiteratureAgent().cite(manifest, knowledge_cache)
