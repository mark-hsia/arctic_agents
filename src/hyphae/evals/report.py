"""Render a :class:`BenchmarkResult` as Markdown.

Formats:
  * one section per benchmark;
  * per-stage table comparing paper value to Hyphae value with pass/fail;
  * summary line with overall pass fraction.
"""

from __future__ import annotations

from collections import defaultdict
from io import StringIO

from .benchmarks.base import BenchmarkResult, Direction

_DIR_SYM = {
    Direction.at_least: ">=",
    Direction.at_most: "<=",
    Direction.close_to: "~",
}


def render_markdown(result: BenchmarkResult) -> str:
    out = StringIO()
    out.write(f"# Benchmark: {result.benchmark_id}\n\n")
    out.write(f"**Reference.** {result.paper_reference}  \n")
    if result.paper_doi:
        out.write(f"**DOI.** [{result.paper_doi}](https://doi.org/{result.paper_doi})\n\n")

    by_stage: dict[str, list] = defaultdict(list)
    for r in result.metric_results:
        by_stage[r.check.stage].append(r)

    out.write(
        f"**Score.** {result.n_passed} / {result.n_total} checks passed "
        f"({100 * result.pass_fraction:.1f} %).\n\n"
    )

    for stage, results in by_stage.items():
        out.write(f"## Stage: {stage}\n\n")
        out.write("| Check | Direction | Paper | Hyphae | Δ | Pass |\n")
        out.write("|---|---|---:|---:|---:|:---:|\n")
        for r in results:
            obs = "—" if r.observed is None else f"{r.observed:.4g}"
            paper = f"{r.check.paper_value:.4g}"
            delta = "—" if r.delta is None else f"{r.delta:+.4g}"
            mark = "PASS" if r.passed else "FAIL"
            out.write(
                f"| `{r.check.name}` | {_DIR_SYM[r.check.direction]} | "
                f"{paper}{r.check.units} | {obs}{r.check.units} | {delta} | {mark} |\n"
            )
        out.write("\n")

    if result.notes:
        out.write("## Notes\n\n")
        for n in result.notes:
            out.write(f"- {n}\n")

    return out.getvalue()


def render_combined_markdown(results: list[BenchmarkResult]) -> str:
    out = StringIO()
    out.write("# Hyphae benchmark report\n\n")
    n_pass = sum(r.n_passed for r in results)
    n_tot = sum(r.n_total for r in results)
    out.write(
        f"**Combined score.** {n_pass} / {n_tot} checks passed "
        f"({100 * (n_pass / n_tot if n_tot else 0):.1f} %) "
        f"across {len(results)} benchmarks.\n\n"
    )
    for r in results:
        out.write(render_markdown(r))
        out.write("\n---\n\n")
    return out.getvalue()
