# Validation Instance — Arctic *Cladonia* Antifungal Discovery

The Arctic *Cladonia* project is the first end-to-end validation of Hyphae. This document specifies how the agent platform exercises every component, what counts as success, and what we are explicitly not claiming.

The science is unchanged from the original proposal: *competition among coexisting fungi within Arctic Cladonia thalli may drive evolution of novel secondary metabolites that serve as antifungal leads.* What changes is the **control layer** that drives the analysis.

## 1. Why this is a good validation case

- **Ground truth exists.** Lichen secondary metabolism is well-characterized for marker compounds (usnic acid, atranorin, fumarprotocetraric acid, etc.). A good platform should rediscover them.
- **Genuine orphan signal is plausible.** Arctic *Cladonia* metagenomes are under-mined; there is a real chance Hyphae surfaces uncharacterized chemistry, not just rediscovers it.
- **Stresses every agent.** Public + field data, mixed assembly quality, eukaryote-heavy metagenomes, fungal targets, and a need for confident-vs-uncertain calls — every agent gets exercised.
- **Constrained scope.** Antifungal target pack is well-defined (CYP51, β-1,3-glucan synthase, Hsp90, Erg-pathway), keeping the Target & Docking agent honest.

## 2. Mapping each project step to Hyphae agents

| Original step (Hsia & Gensbigler timeline) | Hyphae agent path |
|---|---|
| Public Arctic Cladonia data ingestion | Coordinator → Ingestion (SRA / MGnify / JGI) |
| Quality filtering, metaSPAdes assembly | Ingestion → Assembly & Binning |
| EukRep, MetaBAT2 / CONCOCT, DAS Tool, CheckM, BUSCO | Assembly & Binning (multi-tool, agent-chosen parameters) |
| Fungal diversity per sample | Taxonomy & Ecology |
| antiSMASH, DeepBGC, BiG-SCAPE, MIBiG comparison | BGC Discovery + Novelty Assessment |
| Site prioritization model (regression on diversity / BGC abundance / orphan fraction + metadata) | **Coordinator-level decision** drawing on Novelty Assessment + Ecology summaries, with a written rationale instead of a single regression |
| Field sampling at the prioritized site | (Wet-lab, unchanged) |
| Field samples re-run through pipeline | Same Ingestion entry point — no special-case code |
| Orphan BGC structure inference (PRISM/antiSMASH) | Structure Inference |
| Physicochemical filtering, AutoDock Vina docking against *C. albicans* | Target & Docking |
| Compound ranking | Target & Docking + Literature + Critic + Reporter |

The Critic and Reporter are new responsibilities not present in the original proposal; they are the mechanism by which "agentic" stops being a marketing claim.

## 3. Concrete success criteria

Validation passes when **all** of the following hold on a frozen evaluation set of public Cladonia metagenomes plus the field samples (when collected):

### 3.1 Rediscovery (sanity)

- Hyphae recovers ≥ 90% of expected marker BGCs in the public datasets where they are reasonably assemblable (usnic acid PKS, atranorin pathway, etc.) at MAG completeness ≥ 70%.
- The Novelty agent correctly classifies these as *known* (not orphan) ≥ 95% of the time.

### 3.2 Novelty calibration

- On a held-out set of MIBiG-vs-recently-curated-orphan clusters, Novelty Assessment reaches AUROC ≥ 0.85 with calibrated uncertainty (expected calibration error ≤ 0.05).
- Manual triage by the team on the top 25 orphan calls per dataset agrees with Hyphae's ranking on ≥ 70% of items at Spearman ρ ≥ 0.6.

### 3.3 Structure inference discipline

- For BGCs where a published characterized homolog exists, the Structure Inference agent's top-1 SMILES is within Tanimoto ≥ 0.6 of the published structure on ≥ 60% of cases — or the agent correctly emits low confidence.
- Zero high-confidence structures are produced for ribosomal/uncharacterized-class BGCs without explicit Critic waivers.

### 3.4 Docking ranking sanity

- Top-ranked compounds against *C. albicans* CYP51 enrich for known azole-like scaffolds at rates above random (precision-at-K vs. random shuffle, K=20).
- Docking score is not the sole driver of final ranks: the platform's combined ranking deviates from raw docking by a measurable, defensible margin tied to literature evidence.

### 3.5 Field-vs-public consistency

- For the field-sampled site, fungal diversity and BGC abundance fall within the prediction interval generated from public data analysis (i.e., the Coordinator's site-prioritization rationale is not falsified).
- Discrepancies, if any, are surfaced by the Critic with a hypothesis (contamination? sampling depth? seasonal shift?), not buried.

### 3.6 Auditability

- 100% of claims in `report/whitepaper.md` are backed by a rationale and (where applicable) a citation. Run a script that pattern-matches assertions against `rationales[]`; any unmatched claim fails CI.
- Re-running with the same Intent and the same input hashes reproduces the report bit-for-bit in deterministic mode.

## 4. Baselines

Hyphae's value claim must beat a fixed-pipeline baseline that mirrors the original proposal:

- **Baseline A (fixed pipeline).** metaSPAdes + MetaBAT2 + DAS Tool → antiSMASH + DeepBGC → BiG-SCAPE → simple regression for site prioritization → AutoDock Vina against CYP51.
- **Baseline B (LLM-only).** Same data into a single frontier model with tool access but no agent decomposition or critic loop.

Hyphae must (a) match Baseline A on rediscovery, (b) outperform Baseline A on calibrated novelty and on rationale quality (human-rated, blinded), and (c) outperform Baseline B on factuality (citation-backed claims, hallucinated structures).

## 5. What we are explicitly not claiming

- **Not a wet-lab validation.** Top candidates are leads, not validated antifungals.
- **Not clinical relevance.** Docking against CYP51 does not imply efficacy or selectivity.
- **Not a comprehensive Arctic survey.** The eval is bounded by the public datasets and field samples we actually run.
- **Not generality, yet.** Generality to non-antifungal NPD or non-lichen ecosystems is an architectural claim made in [`design.md`](design.md), not a validated one.

## 6. Validation deliverables

Aligned with the original proposal's deliverables, restated under Hyphae:

- **White paper.** Auto-drafted by the Reporter, edited by the team. Every claim cited.
- **Open-source pipeline.** The Hyphae repo itself, with frozen MCP server versions and golden-run inputs.
- **Datasets.** Field metagenomes deposited to NCBI SRA; MAGs and BGC catalogs deposited to appropriate repositories; run cards published.
- **Prioritized candidate list.** Top antifungal candidates with full per-candidate dossiers, ranked, with explicit confidence and the standard "docking-is-ranking-not-validation" disclaimer.

## 7. Risks and how the platform should surface them

| Risk | Surfaced by | Mitigation |
|---|---|---|
| Low-coverage Arctic samples → fragmented BGCs | Assembly & Binning agent | Re-bin, raise novelty uncertainty, defer structure inference. |
| Contamination inflates orphan-BGC count | Taxonomy + Critic | Tetranucleotide-frequency check, contamination flag in rationale. |
| Hallucinated structures from sparse domain logic | Structure Inference + Critic | Confidence floor; Literature agent veto. |
| Field samples dominated by non-Cladonia microbiota | Taxonomy & Ecology | Per-sample fungal-fraction report; Coordinator can re-scope. |
| Overconfident "antifungal lead" framing | Reporter + Critic | Mandatory disclaimer; calibrated uncertainty surfaced in headline. |
