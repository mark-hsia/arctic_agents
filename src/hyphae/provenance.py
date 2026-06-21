"""DuckDB-backed provenance index.

Stores a row per artifact and per rationale, plus the parent-child edges
needed to answer 'why does this number exist?' questions in the report.

We deliberately keep this independent of :class:`ArtifactStore` so we can
re-index a store from scratch by walking files (useful when restoring from
backup).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

import duckdb

from .state import Artifact, Rationale

_SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id     TEXT PRIMARY KEY,
    sha256          TEXT NOT NULL,
    path            TEXT NOT NULL,
    producer_agent  TEXT NOT NULL,
    run_id          TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL,
    tool_version    TEXT,
    mime_type       TEXT,
    bytes           BIGINT,
    metadata        JSON
);

CREATE TABLE IF NOT EXISTS artifact_parents (
    child_id   TEXT NOT NULL,
    parent_id  TEXT NOT NULL,
    PRIMARY KEY (child_id, parent_id)
);

CREATE TABLE IF NOT EXISTS rationales (
    rationale_id     TEXT PRIMARY KEY,
    producer_agent   TEXT NOT NULL,
    claim            TEXT NOT NULL,
    accepted         BOOLEAN NOT NULL,
    critic_comments  JSON,
    created_at       TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS rationale_evidence (
    rationale_id  TEXT NOT NULL,
    artifact_id   TEXT,
    evidence_rationale_id TEXT
);
"""


class ProvenanceIndex:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self.db_path))
        self._conn.execute(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # -- writes ------------------------------------------------------------ #

    def record_artifact(self, artifact: Artifact) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO artifacts
            (artifact_id, sha256, path, producer_agent, run_id, created_at,
             tool_version, mime_type, bytes, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                artifact.artifact_id,
                artifact.sha256,
                artifact.path,
                artifact.producer_agent,
                artifact.run_id,
                artifact.created_at,
                artifact.tool_version,
                artifact.mime_type,
                artifact.bytes,
                json.dumps(artifact.metadata),
            ],
        )
        for parent in artifact.parent_ids:
            self._conn.execute(
                "INSERT OR IGNORE INTO artifact_parents (child_id, parent_id) VALUES (?, ?)",
                [artifact.artifact_id, parent],
            )

    def record_artifacts(self, artifacts: Iterable[Artifact]) -> None:
        for a in artifacts:
            self.record_artifact(a)

    def record_rationale(self, rationale: Rationale) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO rationales
            (rationale_id, producer_agent, claim, accepted, critic_comments, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                rationale.rationale_id,
                rationale.producer_agent,
                rationale.claim,
                rationale.accepted,
                json.dumps(rationale.critic_comments),
                rationale.created_at,
            ],
        )
        self._conn.execute(
            "DELETE FROM rationale_evidence WHERE rationale_id = ?",
            [rationale.rationale_id],
        )
        for art_id in rationale.evidence_artifact_ids:
            self._conn.execute(
                "INSERT INTO rationale_evidence (rationale_id, artifact_id) VALUES (?, ?)",
                [rationale.rationale_id, art_id],
            )
        for ev_rat in rationale.evidence_rationale_ids:
            self._conn.execute(
                "INSERT INTO rationale_evidence (rationale_id, evidence_rationale_id) VALUES (?, ?)",
                [rationale.rationale_id, ev_rat],
            )

    # -- reads ------------------------------------------------------------- #

    def parents_of(self, artifact_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT parent_id FROM artifact_parents WHERE child_id = ?", [artifact_id]
        ).fetchall()
        return [r[0] for r in rows]

    def descendants_of(self, artifact_id: str) -> list[str]:
        rows = self._conn.execute(
            """
            WITH RECURSIVE descendants(child_id) AS (
                SELECT child_id FROM artifact_parents WHERE parent_id = ?
                UNION
                SELECT ap.child_id
                FROM artifact_parents ap
                JOIN descendants d ON ap.parent_id = d.child_id
            )
            SELECT DISTINCT child_id FROM descendants
            """,
            [artifact_id],
        ).fetchall()
        return [r[0] for r in rows]

    def n_artifacts(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]

    def n_rationales(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM rationales").fetchone()[0]

    def rationales_for(self, agent: str) -> list[Rationale]:
        rows = self._conn.execute(
            """
            SELECT rationale_id, producer_agent, claim, accepted, critic_comments, created_at
            FROM rationales WHERE producer_agent = ?
            """,
            [agent],
        ).fetchall()
        out: list[Rationale] = []
        for rid, agent_, claim, accepted, critic_json, created_at in rows:
            evidence = self._conn.execute(
                """
                SELECT artifact_id, evidence_rationale_id FROM rationale_evidence
                WHERE rationale_id = ?
                """,
                [rid],
            ).fetchall()
            art_ids = [e[0] for e in evidence if e[0] is not None]
            ev_rats = [e[1] for e in evidence if e[1] is not None]
            out.append(
                Rationale(
                    rationale_id=rid,
                    producer_agent=agent_,
                    claim=claim,
                    accepted=accepted,
                    critic_comments=json.loads(critic_json) if critic_json else [],
                    created_at=created_at,
                    evidence_artifact_ids=art_ids,
                    evidence_rationale_ids=ev_rats,
                )
            )
        return out
