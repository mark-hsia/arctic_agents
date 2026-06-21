from hyphae.evals.metrics import (
    bgc_class_distribution,
    bgc_count_by_sample,
    fungal_shannon_per_sample,
    named_bgc_recovery,
    t1pks_count_by_sample,
)
from hyphae.state import (
    BGC,
    MAG,
    AssemblyResult,
    BGCClass,
    Intent,
    RunState,
    TaxonomyCall,
)


def _state_with(*, mags: list[MAG], bgcs: list[BGC], taxonomy: dict[str, TaxonomyCall] | None = None) -> RunState:
    return RunState(
        run_id="r",
        intent=Intent(),
        mags=mags,
        bgcs=bgcs,
        taxonomy=taxonomy or {},
        assemblies={
            m.sample_id: AssemblyResult(
                sample_id=m.sample_id,
                assembler="metaspades",
                assembly_artifact_id="a",
            )
            for m in mags
        },
    )


def test_bgc_count_by_sample_groups_via_mag() -> None:
    mags = [
        MAG(mag_id="M_A", sample_id="L1", binner="metabat2", fasta_artifact_id="a"),
        MAG(mag_id="M_B", sample_id="L2", binner="metabat2", fasta_artifact_id="a"),
    ]
    bgcs = [
        BGC(bgc_id="B1", mag_id="M_A", contig="c", start=0, end=10, bgc_class=BGCClass.t1pks),
        BGC(bgc_id="B2", mag_id="M_A", contig="c", start=20, end=30, bgc_class=BGCClass.nrps),
        BGC(bgc_id="B3", mag_id="M_B", contig="c", start=0, end=10, bgc_class=BGCClass.t1pks),
    ]
    state = _state_with(mags=mags, bgcs=bgcs)
    assert bgc_count_by_sample(state) == {"L1": 2, "L2": 1}
    assert t1pks_count_by_sample(state) == {"L1": 1, "L2": 1}
    dist = bgc_class_distribution(state, sample_id="L1")
    assert dist[BGCClass.t1pks] == 1
    assert dist[BGCClass.nrps] == 1


def test_named_bgc_recovery_substring_match() -> None:
    mags = [MAG(mag_id="M1", sample_id="S1", binner="metabat2", fasta_artifact_id="a")]
    bgcs = [
        BGC(
            bgc_id="BGC_grayanic",
            mag_id="M1",
            contig="c",
            start=0,
            end=10,
            bgc_class=BGCClass.t1pks,
            product="grayanic acid",
        ),
        BGC(
            bgc_id="BGC_unknown",
            mag_id="M1",
            contig="c",
            start=20,
            end=30,
            bgc_class=BGCClass.terpene,
        ),
    ]
    state = _state_with(mags=mags, bgcs=bgcs)
    rec = named_bgc_recovery(state, ["grayanic acid", "FR901512"])
    assert rec["grayanic acid"] is True
    assert rec["FR901512"] is False


def test_fungal_shannon_per_sample_uses_taxonomy() -> None:
    mags = [
        MAG(mag_id=f"M{i}", sample_id="S1", binner="metabat2", fasta_artifact_id="a", is_fungal=True)
        for i in range(4)
    ]
    taxonomy = {
        "M0": TaxonomyCall(mag_id="M0", domain="Eukaryota", genus="Cladonia"),
        "M1": TaxonomyCall(mag_id="M1", domain="Eukaryota", genus="Lecanora"),
        "M2": TaxonomyCall(mag_id="M2", domain="Eukaryota", genus="Cladonia"),
        "M3": TaxonomyCall(mag_id="M3", domain="Eukaryota", genus="Lecanora"),
    }
    state = _state_with(mags=mags, bgcs=[], taxonomy=taxonomy)
    h = fungal_shannon_per_sample(state)
    # 2 genera, equal counts -> ln(2)
    assert abs(h["S1"] - 0.6931) < 1e-3
