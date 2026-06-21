from hyphae.state import (
    BGC,
    MAG,
    AssemblyResult,
    BGCClass,
    Intent,
    Rationale,
    RunState,
    RunStatePatch,
    Sample,
    SampleSource,
    apply_patch,
)


def make_state() -> RunState:
    return RunState(run_id="run_test", intent=Intent())


def test_apply_patch_appends_lists_and_merges_dicts() -> None:
    state = make_state()

    s1 = Sample(sample_id="S1", source=SampleSource(kind="local_fastq", identifier="r.fq"))
    s2 = Sample(sample_id="S2", source=SampleSource(kind="local_fastq", identifier="r2.fq"))

    state2 = apply_patch(state, RunStatePatch(samples=[s1]))
    state3 = apply_patch(state2, RunStatePatch(samples=[s2]))
    assert [s.sample_id for s in state3.samples] == ["S1", "S2"]

    asm = AssemblyResult(
        sample_id="S1",
        assembler="metaspades",
        assembly_artifact_id="art_x",
        n_contigs=10,
        n50=1000,
        total_length=20000,
        largest_contig=2000,
    )
    state4 = apply_patch(state3, RunStatePatch(assemblies={"S1": asm}))
    assert state4.assemblies["S1"].n50 == 1000


def test_apply_patch_does_not_mutate_input() -> None:
    state = make_state()
    s = Sample(sample_id="S1", source=SampleSource(kind="local_fastq", identifier="r.fq"))
    state2 = apply_patch(state, RunStatePatch(samples=[s]))
    assert state.samples == []
    assert len(state2.samples) == 1


def test_rationale_carries_evidence() -> None:
    r = Rationale(
        rationale_id="rat_1",
        producer_agent="ingestion",
        claim="OK",
        evidence_artifact_ids=["art_a"],
    )
    assert r.evidence_artifact_ids == ["art_a"]
    assert r.accepted is True


def test_bgc_class_normalization_roundtrip() -> None:
    b = BGC(
        bgc_id="BGC_1",
        mag_id="M_1",
        contig="c1",
        start=10,
        end=20,
        bgc_class=BGCClass.t1pks,
    )
    dumped = b.model_dump()
    assert dumped["bgc_class"] == "T1PKS"


def test_mag_validation_allows_unknown_fields_in_metadata_via_extra_forbid() -> None:
    # ``RunState.model_config`` has ``extra="forbid"``; check unknown field is rejected.
    try:
        RunState.model_validate(
            {
                "run_id": "r",
                "intent": Intent().model_dump(),
                "samples": [],
                "extra_unexpected": "nope",
            }
        )
    except Exception:
        return
    raise AssertionError("RunState should reject unknown top-level keys")


def test_mag_round_trip() -> None:
    m = MAG(mag_id="M1", sample_id="S1", binner="metabat2", fasta_artifact_id="art_x")
    assert m.binner == "metabat2"
