from .base import Benchmark, BenchmarkResult, Direction, MetricCheck, MetricResult
from .junttila2021 import Junttila2021Benchmark
from .lee2024 import Lee2024Benchmark
from .tagirdzhanova2025 import Tagirdzhanova2025Benchmark


def all_benchmarks() -> list[Benchmark]:
    return [
        Junttila2021Benchmark(),
        Tagirdzhanova2025Benchmark(),
        Lee2024Benchmark(),
    ]


__all__ = [
    "Benchmark",
    "BenchmarkResult",
    "Direction",
    "Junttila2021Benchmark",
    "Lee2024Benchmark",
    "MetricCheck",
    "MetricResult",
    "Tagirdzhanova2025Benchmark",
    "all_benchmarks",
]
