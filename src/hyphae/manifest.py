"""Manifest: runtime record of execution, artifacts, and decisions."""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Any
import json


@dataclass
class StepResult:
    """Record of a single tool execution."""
    step_name: str
    tool_id: str
    output_paths: List[Path] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    tool_version: str = "unknown"
    duration_seconds: float = 0.0
    status: str = "pending"

    def to_dict(self) -> dict:
        return {
            "step_name": self.step_name,
            "tool_id": self.tool_id,
            "output_paths": [str(p) for p in self.output_paths],
            "metrics": self.metrics,
            "tool_version": self.tool_version,
            "duration_seconds": self.duration_seconds,
            "status": self.status,
        }


@dataclass
class Artifact:
    """Tracked output file from a tool."""
    artifact_id: str
    path: str
    producer_agent: str
    mime_type: str = "application/octet-stream"
    sha256: str = ""
    bytes: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Rationale:
    """Decision explanation from planner or executor."""
    rationale_id: str
    producer_agent: str
    claim: str
    evidence_artifact_ids: List[str] = field(default_factory=list)
    evidence_rationale_ids: List[str] = field(default_factory=list)
    accepted: bool = True
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BudgetEntry:
    """Resource consumption tracking."""
    agent: str
    tokens: int = 0
    dollars: float = 0.0
    wall_clock_seconds: float = 0.0
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Manifest:
    """Complete execution record: plans, results, decisions, artifacts."""
    run_id: str = ""
    intent: Dict[str, Any] = field(default_factory=dict)
    steps: List[StepResult] = field(default_factory=list)
    artifacts: List[Artifact] = field(default_factory=list)
    rationales: List[Rationale] = field(default_factory=list)
    budget_entries: List[BudgetEntry] = field(default_factory=list)
    final_state: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def empty(cls, run_id: str = "run_new") -> Manifest:
        return cls(run_id=run_id)

    @classmethod
    def from_json(cls, path: Path) -> Manifest:
        data = json.loads(path.read_text())
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> Manifest:
        steps = [StepResult(**s) for s in data.get("steps", [])]
        artifacts = [Artifact(**a) for a in data.get("artifacts", [])]
        rationales = [Rationale(**r) for r in data.get("rationales", [])]
        budget_entries = [BudgetEntry(**b) for b in data.get("budget_entries", [])]
        
        return cls(
            run_id=data.get("run_id", "run_unknown"),
            intent=data.get("intent", {}),
            steps=steps,
            artifacts=artifacts,
            rationales=rationales,
            budget_entries=budget_entries,
            final_state=data.get("final_state", {}),
        )

    def write_json(self, path: Path) -> None:
        payload = {
            "run_id": self.run_id,
            "intent": self.intent,
            "steps": [s.to_dict() for s in self.steps],
            "artifacts": [a.to_dict() for a in self.artifacts],
            "rationales": [r.to_dict() for r in self.rationales],
            "budget_entries": [b.to_dict() for b in self.budget_entries],
            "final_state": self.final_state,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))

    def add_step(self, step: StepResult) -> None:
        self.steps.append(step)

    def add_artifact(self, artifact: Artifact) -> None:
        self.artifacts.append(artifact)

    def add_rationale(self, rationale: Rationale) -> None:
        self.rationales.append(rationale)

    def add_budget_entry(self, entry: BudgetEntry) -> None:
        self.budget_entries.append(entry)
