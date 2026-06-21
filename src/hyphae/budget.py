"""Budget ledger.

Every agent declares a budget; the Coordinator aborts if the run is going to
exceed it. Token / dollar / wall-clock are tracked independently.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .state import Budget, BudgetEntry


@dataclass
class BudgetLedger:
    budget: Budget
    by_agent: dict[str, list[BudgetEntry]] = field(default_factory=lambda: defaultdict(list))

    def charge(
        self,
        agent: str,
        tokens: int = 0,
        dollars: float = 0.0,
        wall_clock_seconds: float = 0.0,
    ) -> BudgetEntry:
        entry = BudgetEntry(
            agent=agent,
            tokens=tokens,
            dollars=dollars,
            wall_clock_seconds=wall_clock_seconds,
        )
        self.by_agent[agent].append(entry)
        return entry

    @property
    def total_tokens(self) -> int:
        return sum(e.tokens for entries in self.by_agent.values() for e in entries)

    @property
    def total_dollars(self) -> float:
        return sum(e.dollars for entries in self.by_agent.values() for e in entries)

    @property
    def total_wall_clock(self) -> float:
        return sum(e.wall_clock_seconds for entries in self.by_agent.values() for e in entries)

    def remaining(self) -> dict[str, float]:
        return {
            "tokens": float(self.budget.max_tokens - self.total_tokens),
            "dollars": float(self.budget.max_dollars - self.total_dollars),
            "wall_clock_seconds": float(
                self.budget.max_wall_clock_seconds - self.total_wall_clock
            ),
        }

    def over_budget(self) -> bool:
        r = self.remaining()
        return any(v < 0 for v in r.values())

    def all_entries(self) -> list[BudgetEntry]:
        out: list[BudgetEntry] = []
        for entries in self.by_agent.values():
            out.extend(entries)
        out.sort(key=lambda e: e.created_at)
        return out
