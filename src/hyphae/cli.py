"""Hyphae command-line interface.

Subcommands:
  hyphae init <workdir> <intent.yaml>  — scaffold a workdir from an intent file.
  hyphae run --workdir DIR              — run the default pipeline.
  hyphae bench --workdir DIR            — score the run state against benchmarks.
  hyphae artifacts ls --workdir DIR     — list artifacts via the provenance index.
  hyphae tools                          — print tool availability matrix.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table

from .evals import all_benchmarks, render_combined_markdown
from .provenance import ProvenanceIndex
from .runner import make_run, run_default_pipeline
from .state import Intent, RunState
from .tools import default_registry

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


@app.command()
def init(
    workdir: Path = typer.Argument(..., help="Working directory to scaffold."),
    intent: Path = typer.Argument(..., help="YAML or JSON intent file."),
) -> None:
    """Initialize a workdir and copy an intent file."""
    workdir = workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    raw = intent.read_text()
    parsed = yaml.safe_load(raw) if intent.suffix in {".yml", ".yaml"} else json.loads(raw)
    intent_obj = Intent.model_validate(parsed)
    (workdir / "intent.json").write_text(intent_obj.model_dump_json(indent=2))
    console.print(f"[green]Initialized workdir at[/green] {workdir}")


@app.command()
def run(
    workdir: Path = typer.Option(..., help="Working directory for the run."),
    intent: Path | None = typer.Option(None, help="Optional intent override."),
    replay: Path | None = typer.Option(None, help="Replay manifest JSON."),
    manifest_path: Path | None = typer.Option(
        None,
        "--manifest-path",
        help="Write a replay manifest JSON to the given path (for later deterministic replay).",
    ),
    deterministic: bool = typer.Option(False, help="Pin seeds, replay-only mode."),
) -> None:
    """Run the default pipeline."""
    workdir = workdir.resolve()
    intent_path = intent or workdir / "intent.json"
    intent_obj = Intent.model_validate(json.loads(intent_path.read_text()))
    hrun, initial = make_run(
        workdir,
        intent_obj,
        replay_manifest=replay,
        deterministic=deterministic,
        manifest_path=manifest_path,
    )
    result = run_default_pipeline(hrun, initial)
    final = result.final_state
    (workdir / "run_state.json").write_text(final.model_dump_json(indent=2))
    hrun.final_state = final

# If the user asked for a manifest, write it now.
    if manifest_path:
        try:
            hrun.write_manifest()
            console.print(f"[green]Manifest written to {manifest_path}[/green]")
        except Exception as exc:
            console.print(f"[red]Failed to write manifest: {exc}[/red]")
    console.print(
        f"[green]Run {hrun.run_id} complete[/green]: "
        f"{len(final.samples)} samples, {len(final.mags)} MAGs, "
        f"{len(final.bgcs)} BGCs."
    )


@app.command()
def bench(
    workdir: Path = typer.Option(..., help="Workdir containing run_state.json."),
    out: Path = typer.Option(
        Path("benchmark_report.md"), help="Output markdown report path."
    ),
) -> None:
    """Score ``run_state.json`` against all benchmarks."""
    state = RunState.model_validate(
        json.loads((workdir / "run_state.json").read_text())
    )
    results = [b.evaluate(state) for b in all_benchmarks()]
    out.write_text(render_combined_markdown(results))
    n_pass = sum(r.n_passed for r in results)
    n_tot = sum(r.n_total for r in results)
    console.print(f"[bold]Benchmark[/bold]: {n_pass}/{n_tot} passed. Report -> {out}")


@app.command("artifacts")
def artifacts_ls(
    workdir: Path = typer.Option(..., help="Workdir."),
) -> None:
    """List artifacts and rationales via the provenance index."""
    prov = ProvenanceIndex(workdir / "provenance.duckdb")
    n_a = prov.n_artifacts()
    n_r = prov.n_rationales()
    table = Table(title="Provenance summary")
    table.add_column("Counter")
    table.add_column("Value", justify="right")
    table.add_row("artifacts", str(n_a))
    table.add_row("rationales", str(n_r))
    console.print(table)


@app.command("tools")
def tools_ls() -> None:
    """Show which tool implementations are available in the current env."""
    reg = default_registry()
    table = Table(title="Tool availability")
    table.add_column("tool_id")
    table.add_column("available")
    for tid, ok in reg.availability_report().items():
        table.add_row(tid, "[green]yes[/green]" if ok else "[red]no[/red]")
    console.print(table)


if __name__ == "__main__":  # pragma: no cover
    app()
