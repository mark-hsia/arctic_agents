# Hyphae — Agent Catalog

Each agent below has a fixed contract: the slice of `RunState` it reads, the slice it writes, the tools it may call, the failure modes it must handle, and a prompt skeleton. The Critic and Coordinator are special.

The contracts here are normative — an agent that violates them is rejected by the Critic and the Coordinator replans.

---

## 1. Coordinator

**Role.** Owns the top-level DAG. Decomposes the user's `Intent` into a plan, dispatches agents, handles replans on failure or Critic rejection.

**Reads.** All of `RunState`.
**Writes.** `intent`, `rationales`, plan metadata.
**Tools.** None directly; dispatches other agents.

**Inputs (Intent).**
```python
class Intent(BaseModel):
    target_pathogen: Literal["candida_albicans", "aspergillus_fumigatus", ...]
    target_proteins: list[TargetProtein]      # e.g., CYP51, β-1,3-glucan synthase
    ecosystem: Literal["arctic_cladonia", "marine_sponge", ...]
    sample_sources: list[SampleSource]        # SRA accessions, MGnify IDs, local paths
    novelty_priority: float                   # 0..1, weights orphan BGCs in ranking
    budget: Budget
```

**Failure modes.**
- A specialist agent overruns its budget → Coordinator either re-scopes the task (e.g., subsample reads) or marks the sample as deferred and continues.
- The Critic rejects a key decision N times → Coordinator escalates by relaxing constraints (e.g., expanding the candidate pool) and logs a rationale.

**Prompt skeleton.**
> You are the Coordinator for Hyphae, an antifungal NPD platform. Given the Intent and current RunState, produce the next batch of agent invocations as a JSON DAG. Justify each step in one sentence referencing the Intent and prior rationales. Never invoke tools directly; always dispatch via the agent registry.

---

## 2. Ingestion

**Role.** Fetch reads, normalize metadata, run QC, decide whether each sample is fit for assembly.

**Reads.** `intent.sample_sources`.
**Writes.** `samples`, `artifacts`, `rationales`.
**Tools.** SRA fetch, MGnify API, JGI IMG API, fastp, FastQC, content hasher.

**Decisions it makes.**
- Trim/filter thresholds based on FastQC output.
- Whether to subsample for cost reasons (logs the rationale).
- Whether a sample is too low-quality to proceed (escalates to Coordinator).

**Failure modes.**
- Public dataset withdrawn / 404 → mark missing, continue with the rest, surface in report.
- Mixed library types (paired vs. single-end) → split into per-strategy assembly batches.

---

## 3. Assembly & Binning

**Role.** Produce fungal MAGs from QC'd reads.

**Reads.** `samples`.
**Writes.** `assemblies`, `mags`, `artifacts`, `rationales`.
**Tools.** metaSPAdes, MEGAHIT, EukRep, Tiara, MetaBAT2, CONCOCT, DAS Tool, CheckM2, BUSCO (Ascomycota lineage).

**Decisions it makes.**
- metaSPAdes vs. MEGAHIT based on read count, complexity, and memory budget.
- k-mer ladder choice from N50 estimates.
- Whether to re-bin with different parameters when CheckM2 completeness < threshold.
- Which bins to discard vs. attempt refinement.

**Output invariant.** Only MAGs with CheckM2 completeness ≥ 70% and contamination ≤ 10% advance, unless the Coordinator's Intent explicitly relaxes thresholds (logged).

**Failure modes.**
- Assembly OOM → fall back to MEGAHIT with reduced k-mer set, log rationale.
- All bins fail QC → escalate to Coordinator with diagnostic summary.

---

## 4. Taxonomy & Ecology

**Role.** Assign taxonomy, summarize community structure, flag co-occurrences relevant to the Intent.

**Reads.** `mags`.
**Writes.** `taxonomy`, `rationales`.
**Tools.** EukRep, BUSCO Ascomycota, GTDB-Tk (bacterial context), a small co-occurrence statistics module.

**Decisions it makes.**
- Whether a MAG is fungal with sufficient confidence to advance to BGC analysis.
- Which co-occurrence patterns are biologically interesting (e.g., two competing Ascomycetes within a single thallus) versus spurious.

**Why it matters for the antifungal thesis.** The platform's hypothesis is that fungal–fungal competition drives novel chemistry. This agent makes that hypothesis testable per sample.

---

## 5. BGC Discovery

**Role.** Identify biosynthetic gene clusters across all fungal MAGs and harmonize tool outputs.

**Reads.** `mags`, `taxonomy`.
**Writes.** `bgcs`, `gcfs`, `artifacts`, `rationales`.
**Tools.** antiSMASH (web API preferred), DeepBGC, GECCO, BiG-SCAPE / BiG-SLiCE against MIBiG.

**Decisions it makes.**
- How to merge overlapping calls from antiSMASH/DeepBGC/GECCO (intersection vs. union, with confidence weighting).
- Cluster boundary disagreements between tools.
- When to re-run a tool with different parameters (e.g., relaxed thresholds for partial clusters at contig edges).

**Output invariant.** Each `BGC` carries: predicted product class, domain architecture, source MAG, originating tool(s), confidence, and links to its GCF.

---

## 6. Novelty Assessment

**Role.** Score how novel each BGC is, with a written rationale.

**Reads.** `bgcs`, `gcfs`, knowledge-cache (MIBiG).
**Writes.** `novelty`, `rationales`.
**Tools.** GCF distance metrics, ESM-2 embeddings of biosynthetic proteins, a small ML classifier trained on MIBiG-vs-orphan, a sequence-similarity search against MIBiG.

**Decisions it makes.**
- How to combine GCF distance, domain rarity, and embedding-based outlier scores into a single novelty score with calibrated uncertainty.
- Whether a "novel" call is robust or artifact-driven (e.g., contig-edge truncation).

**Output invariant.** Every `NoveltyScore` is `{score, components, uncertainty, rationale_id}`. The rationale is mandatory.

---

## 7. Structure Inference

**Role.** Predict candidate metabolite structures from BGC domain logic.

**Reads.** `bgcs`, prioritized by `novelty`.
**Writes.** `structures`, `rationales`.
**Tools.** PRISM REST, antiSMASH SMILES output, RDKit, optionally retro-biosynthesis models.

**Decisions it makes.**
- Which BGCs are tractable for structure inference (NRPS/PKS-rich → yes; ribosomal → handled differently).
- How many alternate scaffolds to emit per BGC (top-K with confidence).
- Whether to defer structure inference to a future iteration when domain logic is ambiguous.

**Hard rule.** Any inferred structure entering `structures` must carry a confidence score and a rationale. The Reporter is forbidden from citing structures whose confidence falls below a threshold without an explicit Critic-approved waiver.

---

## 8. Target & Docking

**Role.** Score candidate compounds against fungal therapeutic targets.

**Reads.** `structures`, `intent.target_proteins`.
**Writes.** `docking`, `rationales`.
**Tools.** Target pack (PDB structures, cofactors, known inhibitor SAR), AutoDock Vina, optionally DiffDock for re-ranking, RDKit for ligand prep, a property-filter module (logP, TPSA, PAINS).

**v1 target pack (antifungal).**
- *Candida albicans* CYP51 (lanosterol 14α-demethylase) — azole target.
- *Candida albicans* β-1,3-glucan synthase — echinocandin target.
- *Aspergillus fumigatus* CYP51A.
- *Candida albicans* / *Aspergillus fumigatus* Hsp90 (chaperone, exploratory).
- ergosterol biosynthesis Erg1/Erg6.

**Decisions it makes.**
- Which targets to dock each candidate against (default = all; Coordinator can subset).
- How to combine docking scores across targets and conformers into a single per-compound rank.
- Property-filter policy (PAINS, Lipinski, antifungal-relevant logP/TPSA windows).

**Hard rule.** Docking is a *ranking* signal, not validation. The Reporter must repeat that disclaimer verbatim.

---

## 9. Literature / Knowledge (RAG)

**Role.** Verify novelty claims, surface relevant SAR, and ground every report-level statement in citations.

**Reads.** `bgcs`, `novelty`, `structures`, `docking`.
**Writes.** `literature`, `rationales`.
**Tools.** Local MIBiG / NPAtlas / ChEMBL caches, OpenAlex, Semantic Scholar, PubMed E-utilities, a vector store of indexed full texts where licensed.

**Decisions it makes.**
- Whether a "novel" structure is genuinely uncharacterized.
- Whether a docking-favored compound has prior antifungal SAR worth flagging.
- Which 3–10 references best support each claim.

**Output invariant.** Every claim that appears in the final report has at least one `Citation` entry; otherwise the Reporter rejects it.

---

## 10. Critic / Verifier

**Role.** Adversarial review. Reject sloppy rationales, demand evidence, force replans.

**Reads.** All of `RunState`.
**Writes.** Critic comments attached to rationales; can flip a rationale's `accepted` flag to false.

**Checks (non-exhaustive).**
- Every rationale references the artifacts it depends on.
- Novelty calls are not contradicted by simple BLAST hits.
- Structure-inference confidence is calibrated against MIBiG holdouts.
- Docking ranks are not driven by trivial physicochemical features (logP correlation sanity check).
- The Reporter is not laundering low-confidence outputs into confident prose.

**Escalation.** Critic rejections feed back to the producing agent with a structured complaint. After N rejections, escalates to the Coordinator.

---

## 11. Reporter

**Role.** Produce the human-readable output: a ranked candidate table, per-candidate dossiers, and a white-paper-quality narrative.

**Reads.** Everything; nothing without a rationale and (where applicable) a citation.
**Writes.** A versioned `report/` directory: Markdown + figures + a structured JSON.

**Outputs.**
- `report/summary.md` — top-K candidates with one-paragraph dossiers.
- `report/per_bgc/<bgc_id>.md` — full provenance per BGC.
- `report/whitepaper.md` — narrative draft.
- `report/run_card.json` — machine-readable run summary.

**Hard rules.**
- No claim without citation or artifact reference.
- No structure shown without confidence.
- The "docking is ranking, not validation" disclaimer is mandatory and verbatim.

---

## Tool registry (referenced above)

The tool registry is a small typed catalog mapping `tool_id → MCP endpoint or Python entry point`. Each entry declares input/output schemas, the hosted vs. self-hosted preference, and a content-addressed cache key function. Agents do not import tools directly; they request them by `tool_id`. This is what makes ecosystem and target-pack swaps tractable.
