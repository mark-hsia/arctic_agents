# Hyphae — Platform Design

This document defines the architecture of Hyphae: an agentic platform for antifungal natural-product discovery. It is opinionated and deliberately narrow on scope (antifungal NPD over metagenomic input) so the first version can be built and validated end-to-end.

## 1. Goals and non-goals

**Goals**

- Take metagenomic reads (public or field) plus a fungal therapeutic target and emit a ranked, evidence-backed list of candidate antifungal compounds.
- Make every prioritization decision *auditable*: a written rationale plus a hashed artifact trail.
- Support iteration: re-running a sample with new tools, new targets, or new evidence should not require pipeline edits.
- Generalize, in principle, to other ecosystems (sponges, soil actinomycetes) by swapping configs and tool wrappers — but the v1 surface is antifungal-only.

**Non-goals (v1)**

- Wet-lab validation, structure elucidation by NMR, or clinical pharmacology.
- Antibacterial / anticancer NPD. The agents and contracts are designed to extend, but v1 ships only antifungal target packs.
- Replacing Snakemake/Nextflow. Hyphae *plans* and *reasons*; it delegates heavy compute to a workflow runner.

## 2. Stack decisions

| Concern | Choice | Why |
|---|---|---|
| Orchestrator | **LangGraph** | Explicit state machine, first-class retry/critic loops, good observability. Pydantic AI is a fallback if we want stricter typed contracts. |
| Reasoning models | Frontier API (Anthropic / OpenAI) | Best-in-class planning and tool use for the Coordinator, Critic, Reporter. |
| Embeddings | Open-weight (ESM-2 for proteins, ChemBERTa / MolFormer for SMILES, BGE / nomic for text) | Cheap, deterministic, runs anywhere. |
| Structure inference assist | Open-weight where mature; frontier reasoning only for triage | Avoids hallucination as much as possible; gates outputs through the Literature agent. |
| Tool surface | **MCP servers** (or simple typed Python tools) | Keeps each tool independently testable and swappable. |
| Heavy compute | **Snakemake** for assembly/BGC/docking DAGs | Reproducibility, restartability, caching. |
| Hosted vs. local | **Hosted services first** (antiSMASH web API, MIBiG REST, NPAtlas API, hosted vector DBs); self-hosted fallbacks in containers | Lower ops burden during student-led development. |
| Tabular store | DuckDB + Parquet | Single-binary, zero-ops. |
| Object store | Local filesystem in dev, S3-compatible in prod | Standard. |
| Vector store | LanceDB | Embedded, local, no infra. |
| Compute orchestration | Ray (optional, batch jobs) | Only if parallel fan-out becomes necessary. |

## 3. High-level architecture

```
                    ┌────────────────────┐
                    │   Coordinator      │  plans DAG, replans on failure
                    └─────────┬──────────┘
                              │
   ┌──────────────────────────┼──────────────────────────────────────┐
   │                          │                                       │
   ▼                          ▼                                       ▼
Ingestion       Assembly & Binning ──► Taxonomy & Ecology          BGC Discovery
   │                          │              │                         │
   └──────────────────────────┴──────────────┴─────────────────────────┘
                              │
                              ▼
                    Novelty Assessment ──► Structure Inference ──► Target & Docking
                              │                    │                      │
                              └────────────────────┴──────────────────────┘
                                                   │
                                                   ▼
                              Literature / Knowledge (RAG)  ◄──► Critic
                                                   │
                                                   ▼
                                                Reporter
```

Every arrow is a typed message in the shared **Run State**. Every box is a LangGraph node backed by an agent (LLM + tools) or a deterministic function (e.g., the Snakemake submitter).

## 4. Run State (single source of truth)

A single typed object passed by reference through the graph. Each agent reads/writes a slice it owns; the Critic reads everything.

```python
class RunState(BaseModel):
    run_id: str
    intent: Intent                           # target organism, target protein, ecosystem prior
    samples: list[Sample]                    # ingested + QC'd
    assemblies: dict[str, AssemblyResult]    # keyed by sample_id
    mags: list[MAG]                          # post-bin, post-refinement
    taxonomy: dict[str, TaxonomyCall]        # keyed by mag_id
    bgcs: list[BGC]                          # antiSMASH/DeepBGC/GECCO unioned
    gcfs: list[GeneClusterFamily]            # BiG-SCAPE/BiG-SLiCE clustering
    novelty: dict[str, NoveltyScore]         # keyed by bgc_id
    structures: dict[str, list[InferredStructure]]   # keyed by bgc_id, with confidence
    docking: dict[str, list[DockingResult]]  # keyed by structure_id
    literature: dict[str, list[Citation]]    # keyed by bgc_id or compound
    rationales: list[Rationale]              # written-out decisions, append-only
    artifacts: ArtifactIndex                 # hash, producer, parents, path
    budget: BudgetLedger                     # tokens + dollars + wall-clock
```

Two invariants:

1. **Every entry in `rationales` references the artifacts it depends on.** A rationale without provenance is rejected by the Critic.
2. **Artifacts are immutable and content-addressed.** Re-running with the same inputs hits the cache.

## 5. Agent contract

Every agent is a `LangGraph` node implementing a single `Protocol`:

```python
class Agent(Protocol):
    name: str
    reads: tuple[str, ...]    # state keys it may read
    writes: tuple[str, ...]   # state keys it may write
    tools: tuple[Tool, ...]   # MCP/Python tools it can call

    async def run(self, state: RunState, ctx: AgentContext) -> RunStatePatch: ...
```

This is enforced; an agent that writes outside its `writes` set is a hard error. This is what makes the Critic auditable — you can ask "who decided that?" and get one answer.

Per-agent details live in [`agents.md`](agents.md).

## 6. Orchestration patterns

Three control flow primitives:

- **Sequential pipeline** (Ingestion → Assembly → BGC) — default.
- **Parallel fan-out** (BGC Discovery runs antiSMASH + DeepBGC + GECCO simultaneously, results unioned) — Ray or asyncio.
- **Critic loop** (any agent's output can be rejected by the Critic, sent back with feedback, with a cap of N iterations and an escalation to the Coordinator).

The Coordinator owns the top-level DAG and is the only agent permitted to replan. Replans are themselves logged as rationales.

## 7. Memory

Three tiers, each with a clear role.

1. **Episodic (per-run).** The `RunState` itself, persisted as JSON + Parquet. Re-openable, replayable.
2. **Semantic (cross-run "lessons").** A small LanceDB collection of compact takeaways: e.g., `{context: "low-coverage Cladonia metagenome with high orphan-BGC rate", lesson: "verify against contamination via tetranucleotide frequency before trusting novelty", evidence: [run_ids]}`. Lessons are written by the Critic post-run, retrieved by the Coordinator pre-plan.
3. **Knowledge cache.** Locally indexed MIBiG, NPAtlas, ChEMBL, and a curated antifungal-targets pack. Hit first by the Literature agent before any web call.

## 8. Tooling layer (hosted-first)

Each external tool is fronted by an MCP server with a typed schema. Where a hosted version exists, we use it; otherwise we self-host in a container with the same schema.

Initial v1 catalog:

| Capability | Hosted preferred | Self-hosted fallback |
|---|---|---|
| Read fetch | NCBI SRA Toolkit (cloud), MGnify API, JGI IMG API | — |
| QC | fastp container | fastp container |
| Assembly | — | metaSPAdes / MEGAHIT in container |
| Binning | — | MetaBAT2 + CONCOCT + DAS Tool in container |
| MAG QC | CheckM2 hosted (where available) | CheckM2 / BUSCO container |
| Eukaryote detection | — | EukRep / Tiara container |
| Taxonomy | GTDB-Tk hosted runs | GTDB-Tk container |
| BGC discovery | **antiSMASH web API**, DeepBGC hosted | antiSMASH / DeepBGC / GECCO containers |
| GCF clustering | BiG-SCAPE on MIBiG snapshot | BiG-SCAPE container |
| Compound DBs | MIBiG REST, NPAtlas API, ChEMBL API | local snapshots |
| Structure inference | PRISM REST, antiSMASH SMILES | local PRISM/antiSMASH |
| Property filters | RDKit (in-process) | — |
| Docking | — | AutoDock Vina + DiffDock in container |
| Literature | OpenAlex API, Semantic Scholar API, PubMed E-utilities | — |

Heavy steps (assembly, docking) are submitted by an agent as a Snakemake job spec; the workflow runner returns artifact paths and metrics.

## 9. Evaluation harness

Without an eval harness, this becomes an LLM-flavored placebo. Three layers of evaluation:

1. **Tool-level unit checks.** Pinned reference inputs and expected outputs for each tool wrapper. CI-grade.
2. **Agent-level synthetic tasks.** Each agent has a small benchmark (e.g., the BGC Discovery agent must recover ≥ 95% of a curated BGC set from a known assembly; the Novelty agent must rank a held-out set of MIBiG-vs-novel clusters with AUROC > 0.85).
3. **End-to-end "golden runs".** Published Cladonia or fungal metagenomes with known biosynthetic content (e.g., usnic acid, atranorin pathways). Hyphae must rediscover them and not hallucinate extras.

A baseline-vs-agent comparison runs every CI cycle: the same input through (a) a fixed pipeline that mirrors the original proposal, and (b) Hyphae. We track recall, precision, novelty calibration, and human-rated rationale quality on a fixed sample.

## 10. Cost, safety, and reproducibility controls

- **Budget ledger.** Every agent declares a token + wall-clock + dollar budget. Coordinator aborts and replans on overrun.
- **Tool caching.** All tool calls keyed by content hash; identical inputs return cached outputs.
- **Hallucination gates.** Structure-inference outputs cannot enter the report until the Literature agent has either (a) confirmed novelty against MIBiG/NPAtlas or (b) documented why the candidate is interesting despite a near-match.
- **Determinism modes.** A `--deterministic` flag pins seeds, disables web search, and forces models to temperature 0; used for golden runs and CI.
- **Provenance.** Every artifact carries `{hash, producer_agent, parent_artifacts, run_id, timestamp, tool_version}`. The Reporter cannot cite an artifact without its provenance entry.

## 11. Generality argument (and its limits)

Hyphae generalizes along three axes by changing **config**, not code:

- **Ecosystem** — swap the Ingestion source list and the priors used by the Taxonomy agent.
- **Target organism** — swap the target pack consumed by the Target & Docking agent (proteins, structures, cofactors, known inhibitor SAR).
- **Tool selection** — swap MCP server endpoints in the tool registry.

Limits we are not pretending to handle in v1:

- Eukaryotic-host effects (e.g., human microbiome confounders).
- Non-sequence-based NPD (e.g., starting from MS/MS spectra). Adding GNPS-style mass-spec would require a new ingestion modality and a real engineering investment.

## 12. Out-of-scope but worth noting

Things that are tempting to add and we explicitly defer:

- A self-improving agent that fine-tunes its own prompts via DSPy/RLAIF. Worth piloting once the eval harness is solid; meaningless before.
- A web UI. CLI + JSON run logs are enough for the validation phase.
- Multi-tenant runs. Single-user, single-machine for v1.
