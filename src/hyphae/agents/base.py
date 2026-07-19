"""Agent base class.

Every agent declares the slice of ``RunState`` it reads and writes. The
contract is enforced at runtime: an agent that returns a patch touching keys
outside its declared ``writes`` set is rejected.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..artifacts import ArtifactStore
from ..budget import BudgetLedger
from ..ids import new_rationale_id
from ..provenance import ProvenanceIndex
from ..state import Artifact, Rationale, RunState, RunStatePatch
from ..tools.registry import ToolRegistry
from ..workflows.runner import WorkflowRunner


@dataclass
class AgentContext:
    """Everything an agent needs that isn't part of ``RunState``."""

    run_id: str
    workdir: Path
    artifact_store: ArtifactStore
    provenance: ProvenanceIndex
    budget: BudgetLedger
    tools: ToolRegistry
    runner: WorkflowRunner
    deterministic: bool = False
    step_params: dict[str, Any] = field(default_factory=dict)
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("hyphae"))

    def make_rationale(
        self,
        agent: str,
        claim: str,
        evidence_artifact_ids: list[str] | None = None,
        evidence_rationale_ids: list[str] | None = None,
    ) -> Rationale:
        return Rationale(
            rationale_id=new_rationale_id(agent, claim, deterministic=self.deterministic),
            producer_agent=agent,
            claim=claim,
            evidence_artifact_ids=list(evidence_artifact_ids or []),
            evidence_rationale_ids=list(evidence_rationale_ids or []),
        )

    def record(self, *, artifacts: list[Artifact] | None = None, rationales: list[Rationale] | None = None) -> None:
        for a in artifacts or []:
            self.provenance.record_artifact(a)
        for r in rationales or []:
            self.provenance.record_rationale(r)


class Agent(ABC):
    """Abstract agent.

    Subclasses set:
      * :attr:`name` — short stable identifier.
      * :attr:`reads` — tuple of ``RunState`` keys read.
      * :attr:`writes` — tuple of ``RunStatePatch`` keys written.
      * :attr:`tools` — tuple of ``tool_id`` strings used.
    """

    name: str = "agent"
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()

    @abstractmethod
    def step(self, state: RunState, ctx: AgentContext) -> RunStatePatch: ...

    def validate_patch(self, patch: RunStatePatch) -> None:
        touched = {k for k, v in patch.model_dump(exclude_none=True).items()}
        # Rationales and artifacts may be written by any agent; they are part
        # of the audit trail rather than a per-agent slice.
        free = {"rationales", "artifacts", "budget_entries"}
        forbidden = touched - set(self.writes) - free
        if forbidden:
            raise PermissionError(
                f"Agent '{self.name}' wrote outside its declared slice: {sorted(forbidden)}"
            )
