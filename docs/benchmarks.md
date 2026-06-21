# Hyphae — Benchmarks

We don't ship "agentic" as a marketing claim. Every release runs the same eval harness against published *Cladonia* / lichen BGC papers. This document spells out which papers, what we measure, and what "outperform" means at each stage.

The harness itself is implemented in `src/hyphae/evals/`. Paper numbers live as JSON under `src/hyphae/evals/benchmarks/data/` so they're easy to update when re-reading sources. Every `MetricCheck` carries a stage label (`assembly`, `mag_qc`, `bgc_discovery`, ...) so failures are localized to a stage.

## Primary benchmark — Junttila et al. 2021

> Junttila S, Eltahir AME, Brouwer H et al. *Microbial Communities of Cladonia Lichens and Their Biosynthetic Gene Clusters Potentially Encoding Natural Products.* **Microorganisms** 9(7): 1347 (2021). DOI: [10.3390/microorganisms9071347](https://doi.org/10.3390/microorganisms9071347)

Why this one is primary:

- **Public input data.** Six *Cladonia* shotgun metagenomes from Southern Finland, ENA project [PRJEB34718](https://www.ebi.ac.uk/ena/browser/view/PRJEB34718). Free to re-run.
- **Concrete numbers per sample.** Reported BUSCO Ascomycota completeness (91.5–93.6 %) and BGC counts per sample (28–41 BGCs, 12–28 T1PKS) using fungiSMASH v6.0.0-alpha.
- **Stricter than the standalone antiSMASH numbers** — picking fungiSMASH numbers gives us a tougher target.

### What "outperform" means, stage-by-stage

| Stage | Hyphae must … | Encoded as |
|---|---|---|
| Assembly | Produce assemblies for all six samples. | `total_samples_assembled >= 6` |
| MAG QC | Land at least the paper's BUSCO Ascomycota completeness on the best fungal MAG per sample. | `busco_ascomycota_complete_<sample> >= paper` |
| BGC discovery | Match or exceed the paper's per-sample BGC count from fungiSMASH. | `bgc_count_<sample> >= paper` |
| BGC discovery | Match or exceed the paper's T1PKS count per sample. | `t1pks_count_<sample> >= paper` |
| Run-level | Total BGCs across all samples ≥ paper lower bound (200). | `total_bgcs >= 200` |

### What Hyphae adds on top (qualitatively)

These are not encoded as `at_least` checks because the paper does not report comparable numbers — they are differentiation, surfaced in the run report:

- **Calibrated novelty score** per BGC with components (GCF distance, ML novelty, sequence-similarity to MIBiG).
- **Critic-reviewed rationale** for every prioritization decision.
- **Auditable provenance** — every number traces back to an artifact hash.

## Secondary benchmark — Tagirdzhanova et al. 2025

> Tagirdzhanova G et al. *A reference metagenome sequence of the lichen Cladonia rangiformis.* **BMC Biology** 23: ... (2025). DOI: [10.1186/s12915-025-02428-z](https://doi.org/10.1186/s12915-025-02428-z)

This is a **named-BGC recovery** test. The paper reports a high-quality PacBio HiFi reference metagenome and identifies named BGCs in the mycobiont, including grayanic acid, 6-hydroxymellein, FR901512, and clavaric acid.

### What "outperform" means

| Stage | Check | Threshold |
|---|---|---|
| BGC discovery | Recover each named BGC from the paper. | `named_bgc_recovery::<name> >= 1.0` |
| BGC discovery | Total BGCs at least the paper count. | `total_bgcs_at_least_paper >= 30` |

Differentiation: Hyphae must additionally produce **defensible orphan BGCs** with calibrated novelty scores beyond the named compounds — captured in the report, not gated by an `at_least`.

## Tertiary benchmark — Lee et al. 2024 (per-species ceiling)

> Lee et al. *Comparative genomics of Cladonia species reveals secondary metabolite diversity and putative environmental adaptations.* **Scientific Reports** 14: ... (2024). DOI: [10.1038/s41598-024-51895-x](https://doi.org/10.1038/s41598-024-51895-x)

Six clean *Cladonia* reference **genomes** (not metagenomes) analyzed with antiSMASH fungal v7.0. BGC counts:

| Species | Paper BGCs |
|---|---:|
| C. borealis | 33 |
| C. grayi | 27 |
| C. macilenta | 31 |
| C. metacorallifera | 36 |
| C. rangiferina | 35 |
| C. uncialis | 28 |

This is a **per-species ceiling**: when Hyphae's MAG for one of these species is taxonomically resolved, we expect to land within 10 % of the per-species count using antiSMASH alone, and to **exceed** it once we ensemble with DeepBGC + GECCO (deferred to v0.2).

## Baselines

To make any "agentic wins" claim defensible, two non-agent baselines run on the same inputs every release:

- **Baseline A — fixed pipeline.** metaSPAdes → MetaBAT2 → DAS Tool → antiSMASH → BiG-SCAPE → simple regression for site prioritization. No agent layer, no critic, no rationale generation.
- **Baseline B — LLM-only.** Same data into a single frontier model with tool access but no agent decomposition or critic loop.

Hyphae's required claims:

1. Match Baseline A on rediscovery (assembly stats, BUSCO, BGC counts).
2. Beat Baseline A on calibrated novelty (calibration error, AUROC on MIBiG-vs-orphan holdout) and on rationale quality (human-rated, blinded panel).
3. Beat Baseline B on factuality — citation-backed claims, hallucinated structures.

Baselines A and B are not in this PR. They are wired into the eval harness via the `Benchmark` interface and will be added in v0.2 once the BGC Discovery agent runs against real antiSMASH output.

## How to run benchmarks

```
hyphae init <workdir> examples/junttila2021_intent.yaml
hyphae run --workdir <workdir> [--replay manifest.json] [--deterministic]
hyphae bench --workdir <workdir> --out report.md
```

The `--replay` switch points at a JSON manifest of pre-recorded tool outputs. It exists so the harness can be exercised in CI without bio binaries; for real benchmarking, omit `--replay` and run on a host with the bio toolchain installed (or with the hosted antiSMASH endpoint configured via `HYPHAE_ANTISMASH_URL`).

## Discipline rules

- **Numbers come from JSON files**, not Python. To revisit a paper number, edit `src/hyphae/evals/benchmarks/data/<paper>.json` and the change shows up in `git diff`.
- **No silent metric changes.** Every `MetricCheck` has a `description` that ends up in the rendered report.
- **Failure is OK.** A run with three failed checks is more useful than a run with no checks at all. The eval harness records failures and lets the team decide whether to chase the gap or document the trade-off.
