from pathlib import Path

from hyphae.artifacts import ArtifactStore


def test_put_path_is_content_addressed(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "store")
    src = tmp_path / "x.txt"
    src.write_text("hello")
    a1 = store.put_path(src, producer_agent="t", run_id="r1")
    a2 = store.put_path(src, producer_agent="t", run_id="r2")
    assert a1.sha256 == a2.sha256
    assert store.exists(a1.sha256)
    assert store.resolve(a1).read_text() == "hello"


def test_put_bytes_roundtrip(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "store")
    a = store.put_bytes(b"abc", producer_agent="t", run_id="r")
    assert a.bytes == 3
    assert store.resolve(a).read_bytes() == b"abc"


def test_put_path_with_parents(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "store")
    src = tmp_path / "a.txt"
    src.write_text("data")
    a = store.put_path(src, producer_agent="t", run_id="r", parent_ids=["art_parent"])
    assert a.parent_ids == ["art_parent"]
