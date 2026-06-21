from hyphae.budget import BudgetLedger
from hyphae.state import Budget


def test_budget_charges_and_totals() -> None:
    ledger = BudgetLedger(Budget(max_tokens=1_000, max_dollars=1.0, max_wall_clock_seconds=10))
    ledger.charge("ingestion", tokens=100, dollars=0.1, wall_clock_seconds=2)
    ledger.charge("assembly", tokens=200, wall_clock_seconds=3)
    assert ledger.total_tokens == 300
    assert ledger.total_dollars == 0.1
    assert ledger.total_wall_clock == 5
    assert not ledger.over_budget()


def test_over_budget_flag() -> None:
    ledger = BudgetLedger(Budget(max_tokens=10, max_dollars=1.0, max_wall_clock_seconds=10))
    ledger.charge("ingestion", tokens=100)
    assert ledger.over_budget()
