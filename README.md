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
- [`docs/roadmap.md`](docs/roadmap.md) — June–September plan expressed as agent milestones.

## Status

Design phase. No implementation yet — the documents above are the proposal under review.
