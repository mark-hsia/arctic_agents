"""Typed state model for a Hyphae run.

`RunState` is the single source of truth that flows through the agent graph.
Each agent reads/writes a declared slice of it; mutations happen through
``RunStatePatch`` objects so the orchestrator can record what changed and who
changed it.

The schemas here are deliberately wide: every field is optional so we can ship
partial pipelines (e.g., the June milestone produces ``samples``, ``mags``,
``taxonomy``, ``bgcs`` but not yet ``structures`` or ``docking``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------- #
# Intent / inputs
# --------------------------------------------------------------------------- #


class TargetPathogen(StrEnum):
    candida_albicans = "candida_albicans"
    aspergillus_fumigatus = "aspergillus_fumigatus"
    cryptococcus_neoformans = "cryptococcus_neoformans"


class TargetProtein(BaseModel):
    name: str
    pdb_id: str | None = None
    uniprot_id: str | None = None
    notes: str | None = None


class SampleSource(BaseModel):
    """A pointer to data we can ingest. One of: SRA accession, local FASTQ paths,
    MGnify analysis ID, JGI IMG sample ID."""

    kind: Literal["sra", "ena", "local_fastq", "mgnify", "jgi"]
    identifier: str
    paired: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class Budget(BaseModel):
    max_tokens: int = 1_000_000
    max_dollars: float = 25.0
    max_wall_clock_seconds: int = 60 * 60 * 6


class Intent(BaseModel):
    """The user request. Validated before the Coordinator plans."""

    target_pathogen: TargetPathogen = TargetPathogen.candida_albicans
    target_proteins: list[TargetProtein] = Field(default_factory=list)
    ecosystem: str = "arctic_cladonia"
    sample_sources: list[SampleSource] = Field(default_factory=list)
    novelty_priority: float = Field(default=0.5, ge=0.0, le=1.0)
    budget: Budget = Field(default_factory=Budget)
    deterministic: bool = False
    notes: str | None = None


# --------------------------------------------------------------------------- #
# Per-stage payloads
# --------------------------------------------------------------------------- #


class QcVerdict(StrEnum):
    pass_ = "pass"
    marginal = "marginal"
    fail = "fail"


class Sample(BaseModel):
    sample_id: str
    source: SampleSource
    raw_artifact_ids: list[str] = Field(default_factory=list)
    qc_artifact_id: str | None = None
    qc_verdict: QcVerdict = QcVerdict.pass_
    n_reads: int | None = None
    mean_read_length: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssemblyResult(BaseModel):
    sample_id: str
    assembler: Literal["metaspades", "megahit"]
    assembly_artifact_id: str
    n_contigs: int | None = None
    total_length: int | None = None
    n50: int | None = None
    largest_contig: int | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class MAG(BaseModel):
    mag_id: str
    sample_id: str
    binner: Literal["metabat2", "concoct", "das_tool"]
    fasta_artifact_id: str
    completeness: float | None = None  # CheckM2 / BUSCO
    contamination: float | None = None
    n_contigs: int | None = None
    total_length: int | None = None
    busco_complete: float | None = None  # Ascomycota lineage
    busco_lineage: str | None = None
    is_fungal: bool | None = None  # EukRep / Tiara call


class TaxonomyCall(BaseModel):
    mag_id: str
    domain: Literal["Eukaryota", "Bacteria", "Archaea", "Unknown"] = "Unknown"
    phylum: str | None = None
    class_: str | None = Field(default=None, alias="class")
    order: str | None = None
    family: str | None = None
    genus: str | None = None
    species: str | None = None
    confidence: float | None = None
    method: str | None = None  # e.g., "EukRep+BUSCO_ascomycota", "GTDB-Tk"

    model_config = ConfigDict(populate_by_name=True)


class BGCClass(StrEnum):
    """antiSMASH/DeepBGC class taxonomy, normalized."""

    t1pks = "T1PKS"
    t2pks = "T2PKS"
    t3pks = "T3PKS"
    nrps = "NRPS"
    nrps_like = "NRPS-like"
    pks_nrps_hybrid = "PKS-NRPS_hybrid"
    terpene = "terpene"
    ripp = "RiPP"
    fungal_ripp_like = "fungal-RiPP-like"
    indole = "indole"
    siderophore = "siderophore"
    other = "other"


class BGC(BaseModel):
    bgc_id: str
    mag_id: str
    contig: str
    start: int
    end: int
    bgc_class: BGCClass
    product: str | None = None
    domains: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)  # antiSMASH, DeepBGC, GECCO
    confidence: float | None = None
    gbk_artifact_id: str | None = None
    edge_truncated: bool = False  # contig-edge BGCs often partial


class GeneClusterFamily(BaseModel):
    gcf_id: str
    method: Literal["bigscape", "bigslice"] = "bigscape"
    member_bgc_ids: list[str] = Field(default_factory=list)
    nearest_mibig_id: str | None = None
    nearest_mibig_distance: float | None = None
    is_orphan: bool = False


class NoveltyScore(BaseModel):
    bgc_id: str
    score: float = Field(ge=0.0, le=1.0)
    uncertainty: float = Field(ge=0.0, le=1.0)
    components: dict[str, float] = Field(default_factory=dict)
    rationale_id: str | None = None


class InferredStructure(BaseModel):
    structure_id: str
    bgc_id: str
    smiles: str
    confidence: float
    method: str
    notes: str | None = None


class DockingResult(BaseModel):
    structure_id: str
    target_name: str
    target_pdb_id: str | None
    score: float
    pose_artifact_id: str | None = None
    method: Literal["vina", "diffdock"] = "vina"


class Citation(BaseModel):
    bgc_or_compound_id: str
    title: str
    doi: str | None = None
    url: str | None = None
    year: int | None = None
    snippet: str | None = None


# --------------------------------------------------------------------------- #
# Provenance and rationale
# --------------------------------------------------------------------------- #


class Artifact(BaseModel):
    artifact_id: str  # short id, also primary key
    sha256: str
    path: str  # relative to artifact root
    producer_agent: str
    parent_ids: list[str] = Field(default_factory=list)
    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tool_version: str | None = None
    mime_type: str | None = None
    bytes: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Rationale(BaseModel):
    rationale_id: str
    producer_agent: str
    claim: str
    evidence_artifact_ids: list[str] = Field(default_factory=list)
    evidence_rationale_ids: list[str] = Field(default_factory=list)
    accepted: bool = True
    critic_comments: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BudgetEntry(BaseModel):
    agent: str
    tokens: int = 0
    dollars: float = 0.0
    wall_clock_seconds: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# --------------------------------------------------------------------------- #
# RunState
# --------------------------------------------------------------------------- #


class RunState(BaseModel):
    """Whole-run state. Mutated only via :class:`RunStatePatch`."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    intent: Intent
    samples: list[Sample] = Field(default_factory=list)
    assemblies: dict[str, AssemblyResult] = Field(default_factory=dict)
    mags: list[MAG] = Field(default_factory=list)
    taxonomy: dict[str, TaxonomyCall] = Field(default_factory=dict)
    bgcs: list[BGC] = Field(default_factory=list)
    gcfs: list[GeneClusterFamily] = Field(default_factory=list)
    novelty: dict[str, NoveltyScore] = Field(default_factory=dict)
    structures: dict[str, list[InferredStructure]] = Field(default_factory=dict)
    docking: dict[str, list[DockingResult]] = Field(default_factory=dict)
    literature: dict[str, list[Citation]] = Field(default_factory=dict)
    rationales: list[Rationale] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    budget_entries: list[BudgetEntry] = Field(default_factory=list)


class RunStatePatch(BaseModel):
    """Patches are append-only or whole-key-replace, by design.

    ``samples``, ``mags``, ``bgcs``, ``gcfs``, ``rationales``, ``artifacts``,
    ``budget_entries`` are extended (list append). ``assemblies``, ``taxonomy``,
    ``novelty``, ``structures``, ``docking``, ``literature`` are merged (dict
    update). ``intent`` is immutable post-init and cannot be patched.
    """

    samples: list[Sample] | None = None
    assemblies: dict[str, AssemblyResult] | None = None
    mags: list[MAG] | None = None
    taxonomy: dict[str, TaxonomyCall] | None = None
    bgcs: list[BGC] | None = None
    gcfs: list[GeneClusterFamily] | None = None
    novelty: dict[str, NoveltyScore] | None = None
    structures: dict[str, list[InferredStructure]] | None = None
    docking: dict[str, list[DockingResult]] | None = None
    literature: dict[str, list[Citation]] | None = None
    rationales: list[Rationale] | None = None
    artifacts: list[Artifact] | None = None
    budget_entries: list[BudgetEntry] | None = None


def apply_patch(state: RunState, patch: RunStatePatch) -> RunState:
    """Return a new ``RunState`` with the patch applied. Append-only for lists,
    dict-merge for maps. The original ``state`` is not mutated."""

    data = state.model_dump(by_alias=False)

    list_keys = {
        "samples",
        "mags",
        "bgcs",
        "gcfs",
        "rationales",
        "artifacts",
        "budget_entries",
    }
    dict_keys = {
        "assemblies",
        "taxonomy",
        "novelty",
        "structures",
        "docking",
        "literature",
    }
    patch_dict = patch.model_dump(exclude_none=True)
    for key, value in patch_dict.items():
        if key in list_keys:
            data[key] = list(data.get(key, [])) + list(value)
        elif key in dict_keys:
            merged = dict(data.get(key, {}))
            merged.update(value)
            data[key] = merged
        else:  # pragma: no cover - shouldn't happen with current schema
            raise KeyError(f"Unknown patch key: {key}")
    return RunState.model_validate(data)
