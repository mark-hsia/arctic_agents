# Hyphae — Roadmap (Summer 2026)

This roadmap re-expresses the original Arctic *Cladonia* timeline in terms of agent milestones. The science remains on schedule; the deliverables are reframed as platform capabilities, each validated on the lichen instance.

A guiding principle: **the eval harness comes first, every month.** No agent ships without its synthetic benchmark passing.

## June — Ingestion + Assembly + Taxonomy (foundation) **[scaffolded]**

**Original deliverable.** Metagenomic assembly and fungal diversity reconstruction from public Arctic *Cladonia* datasets.

**Hyphae deliverable.** End-to-end run of the first three agents (Ingestion, Assembly & Binning, Taxonomy & Ecology) on at least one public dataset, with results reproducible in deterministic mode.

**Agent milestones.**
- Coordinator skeleton (LangGraph state machine, RunState defined, dispatch loop).
- Ingestion agent online: SRA / MGnify / JGI fetchers wrapped as MCP tools, fastp QC integrated, sample fitness decisions logged as rationales.
- Assembly & Binning agent online: metaSPAdes + MEGAHIT + MetaBAT2 + CONCOCT + DAS Tool + CheckM2 + BUSCO Ascomycota wrapped; agent picks tool/parameters; re-bin loop implemented.
- Taxonomy & Ecology agent online: EukRep + GTDB-Tk + co-occurrence summary; per-sample fungal community report.
- First version of the eval harness: tool-level unit checks, one synthetic Assembly benchmark, one golden-run input.
- Artifact store + provenance index working end-to-end (DuckDB + Parquet + content-addressed files).

**Exit criterion.** Re-running the same public dataset twice in deterministic mode yields bit-identical artifacts and reports.

**Status (PR #2).** Scaffold + benchmark harness landed:

- Typed `RunState`, content-addressed artifact store, DuckDB provenance index, budget ledger.
- Agent base + Coordinator (LangGraph) + Ingestion + Assembly & Binning + Taxonomy & Ecology + BGC Discovery (antiSMASH-only).
- Tool registry with hosted-first routing; `LocalShellRunner` / `DryRunRunner` / `ReplayRunner`.
- Eval harness with three benchmark specs (Junttila 2021, Tagirdzhanova 2025, Lee 2024); 34-check pytest suite green without any bio tools.
- CLI (`hyphae init / run / bench / artifacts / tools`); GitHub Actions CI.

What is left for June's exit criterion: an actual live run against PRJEB34718 (one sample is enough for the deterministic-replay check). That gates on either a self-hosted bio container or a hosted antiSMASH endpoint, neither of which is in this repo's CI today.

## July — BGC Discovery + Novelty + Coordinator-led prioritization

**Original deliverable.** BGC discovery, site prioritization, top-ranked site selected for field sampling.

**Hyphae deliverable.** End-to-end run produces a ranked list of Arctic sites with a written, auditable rationale per site, plus the Critic's review of that ranking.

**Agent milestones.**
- BGC Discovery agent online: hosted antiSMASH + DeepBGC + GECCO, with a tool-disagreement reconciliation policy; BiG-SCAPE clustering against MIBiG.
- Novelty Assessment agent online: GCF distance + ESM-2 embeddings + small classifier; calibrated uncertainty.
- Coordinator-level site prioritization: replaces the original simple regression. Output is a ranked list with per-site rationales linking diversity, BGC abundance, orphan fraction, and environmental metadata.
- Critic agent online: rationale audit, contamination checks, novelty sanity checks. End-to-end critic loop functioning.
- Eval harness: Novelty AUROC benchmark on MIBiG-vs-orphan holdout; rediscovery test for usnic acid / atranorin pathways on at least one public Cladonia dataset.
- Baseline A (fixed pipeline) and Baseline B (LLM-only) running on the same eval inputs for comparison.

**Exit criterion.** A field-site recommendation with a written rationale that the team would defend in a paper, and Critic-level evidence that Hyphae beats Baseline A on calibrated novelty and Baseline B on factuality.

## August — Field samples through the same agent graph

**Original deliverable.** Field sampling, sequencing, validation against public-data predictions.

**Hyphae deliverable.** Field samples enter through the same Ingestion agent — no special-case code path. Field-vs-public consistency is reported by the Coordinator with the Critic's review.

**Agent milestones.**
- Field sample ingestion: same MCP tool surface, just a local-files source. The fact that this requires *no* new code is a deliverable of the architecture.
- Field-vs-public consistency report: Coordinator generates a structured comparison. Discrepancies surfaced as hypotheses, not buried.
- Eval harness: a "field-mode" run that exercises the platform on the field FASTQ files in deterministic mode.

**Exit criterion.** Field sample run completes end-to-end through the same DAG used in July, and the Critic's review of the consistency report is signed off by the team.

## September — Structure Inference + Docking + Literature + Reporter

**Original deliverable.** Compound prioritization, docking, white paper.

**Hyphae deliverable.** Ranked candidate antifungals against the v1 target pack, full per-candidate dossiers, auto-drafted white paper, every claim cited.

**Agent milestones.**
- Structure Inference agent online: PRISM + antiSMASH SMILES + RDKit; top-K with confidence; explicit deferral path for ambiguous BGCs.
- Target & Docking agent online with the v1 antifungal target pack (CYP51 — *C. albicans* + *A. fumigatus*, β-1,3-glucan synthase, Hsp90, Erg1/Erg6); AutoDock Vina, optionally DiffDock for re-ranking; PAINS/Lipinski filter module.
- Literature / Knowledge agent online: local MIBiG / NPAtlas / ChEMBL caches + OpenAlex + Semantic Scholar + PubMed; novelty verification and SAR surfacing.
- Reporter agent online: per-candidate dossiers, ranked summary, auto-drafted white paper, run card. Citation enforcement and the docking-is-ranking disclaimer hard-coded.
- Final eval harness pass: rediscovery + novelty calibration + structure-inference discipline + docking ranking sanity, all green.
- Baseline A and Baseline B comparison results published in the white paper.

**Exit criterion.** A reproducible end-to-end run producing the deliverable set required by the original proposal — white paper, open-source pipeline, datasets, prioritized candidates — with auditable provenance and the Critic's sign-off.

## Cross-cutting work (continuous, not month-bound)

- **Eval harness.** Grows monthly with each new agent.
- **Cost ledger.** Token / dollar / wall-clock budgets refined as we learn.
- **Determinism mode.** Maintained from June onward; required for any golden run.
- **Documentation.** Every agent's contract is updated when its behavior changes; rationales must remain decodable months later.

## What is intentionally *not* on this roadmap

- DSPy / RLAIF self-tuning loops. Defer until eval harness is mature; meaningless before.
- A web UI. Not on the v1 critical path.
- Mass-spec ingestion (GNPS-style). Architecturally compatible, scoped out for v1.
- Generalization to non-antifungal targets. Possible by config; v1 ships and validates antifungal only.
