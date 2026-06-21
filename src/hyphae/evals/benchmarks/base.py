"""Benchmark base class.

A :class:`Benchmark` declares (a) the inputs it expects, (b) the paper
reference, (c) per-stage expected metrics from the paper, and (d) the
``evaluate(state)`` logic that compares Hyphae's run state to those
expectations and returns a :class:`BenchmarkResult`.

Each metric check is a :class:`MetricCheck`. ``Direction`` says whether we
want to be at least the paper number, at most, or close-to.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ...state import RunState


class Direction(StrEnum):
    at_least = "at_least"
    at_most = "at_most"
    close_to = "close_to"  # within tolerance of paper number


@dataclass
class MetricCheck:
    name: str
    stage: str  # e.g., "ingestion", "assembly", "mag_qc", "bgc_discovery"
    direction: Direction
    paper_value: float
    extractor: Callable[[RunState], float | None]
    tolerance: float = 0.0  # for close_to / fractional slack on at_least/at_most
    units: str = ""
    description: str = ""

    def evaluate(self, state: RunState) -> MetricResult:
        observed = self.extractor(state)
        if observed is None:
            return MetricResult(check=self, observed=None, passed=False, delta=None)
        if self.direction == Direction.at_least:
            passed = observed >= self.paper_value * (1 - self.tolerance)
        elif self.direction == Direction.at_most:
            passed = observed <= self.paper_value * (1 + self.tolerance)
        else:
            passed = abs(observed - self.paper_value) <= self.tolerance
        delta = observed - self.paper_value
        return MetricResult(check=self, observed=observed, passed=passed, delta=delta)


@dataclass
class MetricResult:
    check: MetricCheck
    observed: float | None
    passed: bool
    delta: float | None


@dataclass
class BenchmarkResult:
    benchmark_id: str
    paper_reference: str
    paper_doi: str | None
    metric_results: list[MetricResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def n_passed(self) -> int:
        return sum(1 for r in self.metric_results if r.passed)

    @property
    def n_total(self) -> int:
        return len(self.metric_results)

    @property
    def pass_fraction(self) -> float:
        return self.n_passed / self.n_total if self.n_total else 0.0


class Benchmark(ABC):
    benchmark_id: str = "abstract"
    paper_reference: str = ""
    paper_doi: str | None = None

    @abstractmethod
    def expected(self) -> list[MetricCheck]: ...

    def evaluate(self, state: RunState) -> BenchmarkResult:
        results = [check.evaluate(state) for check in self.expected()]
        return BenchmarkResult(
            benchmark_id=self.benchmark_id,
            paper_reference=self.paper_reference,
            paper_doi=self.paper_doi,
            metric_results=results,
        )

    def inputs(self) -> dict[str, Any]:  # pragma: no cover - per-benchmark override
        return {}
