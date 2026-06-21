# Hyphae

**An agentic platform for antifungal natural-product discovery — validated on Arctic *Cladonia* lichen metagenomes.**

Hyphae takes raw metagenomic data and a fungal therapeutic target, and returns a ranked, evidence-backed list of candidate antifungal compounds with full provenance. The platform is a coordinated team of LLM agents that drive established bioinformatics tools, reason across genomic/chemical/literature evidence, and explain their prioritizations.

The original Arctic *Cladonia* project (Hsia & Gensbigler, Summer 2026) is the first validation instance: same hypothesis, same field plan, but the fixed pipeline is replaced by an agentic control layer that adapts parameters, integrates evidence, and produces auditable decisions.

## Why agents

The original pipeline is linear: assemble → bin → BGC discovery → cluster → dock. Every step uses one tool with one parameter set, and prioritization collapses to a single score. Agents change three things:

1. **Adaptive control.** Pick assemblers, binners, BGC tools, and targets based on the data in front of them, not a hard-coded path.
2. **Cross-modal reasoning.** A "novel" BGC call only earns the label after genomic, chemical, docking, and literature evidence agree.
3. **Auditability and generalization.** Every ranking comes with a written rationale and a hashed artifact trail. Swapping the validation instance (sponges, soil actinomycetes, insect microbiomes) is a config change, not a rewrite.

## Validation instance: Arctic *Cladonia*

We retain the original scientific question — *do competing fungi in Arctic lichen thalli evolve novel secondary metabolites with antifungal potential?* — and run it through Hyphae:

- June: public Arctic metagenomes ingested → fungal MAGs reconstructed.
- July: BGCs discovered, sites ranked **by an agent with a written rationale** instead of a single regression.
- August: field samples flow through the same agent graph as public data.
- September: orphan BGCs scored against *Candida albicans* CYP51 and other clinically relevant targets, ranked, and written up.

Success criteria, baselines, and target metrics live in [`docs/validation_cladonia.md`](docs/validation_cladonia.md).

## Documentation

- [`docs/design.md`](docs/design.md) — architecture, orchestration, state, memory, evaluation.
- [`docs/agents.md`](docs/agents.md) — per-agent contracts, tools, failure modes, prompt skeletons.
- [`docs/validation_cladonia.md`](docs/validation_cladonia.md) — how the Arctic project exercises every agent and what counts as success.
- [`docs/benchmarks.md`](docs/benchmarks.md) — benchmark papers, what we measure, what "outperform" means at each stage.
- [`docs/roadmap.md`](docs/roadmap.md) — June–September plan expressed as agent milestones.

## Status

**June milestone scaffolded.** The foundation, agent layer, and benchmark harness are in. End-to-end runs work against three published *Cladonia* papers — the harness scores Hyphae's run state against their reported numbers stage-by-stage. Bio tool execution (metaSPAdes, antiSMASH, ...) is wired but only fires when the binaries are present; CI exercises the full graph in **replay mode** against pre-recorded artifacts.

**Implemented**

- Typed `RunState` + append-only patch model.
- Content-addressed artifact store and DuckDB provenance index.
- Budget ledger.
- Agent base class enforcing reads/writes contracts.
- Tool registry with hosted-vs-local routing; tool wrappers shell out when binaries present, defer cleanly otherwise.
- Workflow runners: `LocalShellRunner`, `DryRunRunner`, `ReplayRunner` (`SnakemakeRunner` stub).
- Coordinator (LangGraph), Ingestion, Assembly & Binning, Taxonomy & Ecology, BGC Discovery agents.
- Eval harness wired against:
  - **Junttila et al. 2021** — primary head-to-head, six *Cladonia* metagenomes (PRJEB34718).
  - **Tagirdzhanova et al. 2025** — named-BGC recovery on *C. rangiformis*.
  - **Lee et al. 2024** — per-species ceiling on six *Cladonia* genomes.
- CLI: `hyphae init / run / bench / artifacts / tools`.
- Pytest suite (34 checks) + GitHub Actions CI.

**Deferred**

- Real runs against PRJEB34718. Requires hosted antiSMASH credentials or a container with the bio toolchain. The harness flips to live execution by removing `--replay`; no code changes needed.
- DeepBGC, GECCO, BiG-SCAPE wrappers (BGC Discovery v0 is antiSMASH-only).
- Novelty / Structure / Docking / Literature / Critic / Reporter — those are July–September per the roadmap.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                                # 34 checks pass without any bio tools
hyphae tools                          # show which tool wrappers are available
hyphae init out/ examples/junttila2021_intent.yaml
hyphae run --workdir out/ --replay <manifest.json> --deterministic
hyphae bench --workdir out/ --out out/report.md
```
