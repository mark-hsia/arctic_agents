from datetime import UTC, datetime
from pathlib import Path

from hyphae.provenance import ProvenanceIndex
from hyphae.state import Artifact, Rationale


def test_record_and_query(tmp_path: Path) -> None:
    idx = ProvenanceIndex(tmp_path / "p.duckdb")

    parent = Artifact(
        artifact_id="art_p",
        sha256="00",
        path="00/p",
        producer_agent="ingest",
        run_id="r",
        created_at=datetime.now(UTC),
    )
    child = Artifact(
        artifact_id="art_c",
        sha256="11",
        path="11/c",
        producer_agent="assembly",
        run_id="r",
        created_at=datetime.now(UTC),
        parent_ids=["art_p"],
    )
    idx.record_artifact(parent)
    idx.record_artifact(child)

    assert idx.parents_of("art_c") == ["art_p"]
    assert idx.descendants_of("art_p") == ["art_c"]
    assert idx.n_artifacts() == 2

    rat = Rationale(
        rationale_id="rat_1",
        producer_agent="assembly",
        claim="why",
        evidence_artifact_ids=["art_p", "art_c"],
    )
    idx.record_rationale(rat)
    rats = idx.rationales_for("assembly")
    assert len(rats) == 1
    assert set(rats[0].evidence_artifact_ids) == {"art_p", "art_c"}
    idx.close()
