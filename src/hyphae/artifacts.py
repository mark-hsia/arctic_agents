"""Content-addressed artifact store.

Every byte the platform produces lands here, keyed by sha256. The same file
contents from two runs collapse to one artifact; re-running with identical
inputs hits the cache.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from .ids import new_artifact_id
from .state import Artifact


class ArtifactStore:
    """Filesystem-backed content-addressed store.

    Layout::

        <root>/
          ab/<full sha256>   # files split by first 2 hex chars

    Reads and writes are idempotent.
    """

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- internal helpers -------------------------------------------------- #

    def _store_path(self, sha: str) -> Path:
        return self.root / sha[:2] / sha

    @staticmethod
    def _sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _sha256_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    # -- public API -------------------------------------------------------- #

    def put_path(
        self,
        path: Path | str,
        producer_agent: str,
        run_id: str,
        parent_ids: list[str] | None = None,
        tool_version: str | None = None,
        mime_type: str | None = None,
        metadata: dict | None = None,
    ) -> Artifact:
        src = Path(path)
        if not src.is_file():
            raise FileNotFoundError(src)
        sha = self._sha256_file(src)
        dest = self._store_path(sha)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copy2(src, dest)
        return Artifact(
            artifact_id=new_artifact_id(sha),
            sha256=sha,
            path=str(dest.relative_to(self.root)),
            producer_agent=producer_agent,
            parent_ids=list(parent_ids or []),
            run_id=run_id,
            created_at=datetime.now(UTC),
            tool_version=tool_version,
            mime_type=mime_type,
            bytes=os.path.getsize(dest),
            metadata=metadata or {},
        )

    def put_bytes(
        self,
        data: bytes,
        producer_agent: str,
        run_id: str,
        parent_ids: list[str] | None = None,
        tool_version: str | None = None,
        mime_type: str | None = None,
        metadata: dict | None = None,
    ) -> Artifact:
        sha = self._sha256_bytes(data)
        dest = self._store_path(sha)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_bytes(data)
        return Artifact(
            artifact_id=new_artifact_id(sha),
            sha256=sha,
            path=str(dest.relative_to(self.root)),
            producer_agent=producer_agent,
            parent_ids=list(parent_ids or []),
            run_id=run_id,
            created_at=datetime.now(UTC),
            tool_version=tool_version,
            mime_type=mime_type,
            bytes=len(data),
            metadata=metadata or {},
        )

    def resolve(self, artifact: Artifact) -> Path:
        """Absolute path of the stored object."""
        return self.root / artifact.path

    def exists(self, sha256: str) -> bool:
        return self._store_path(sha256).exists()
