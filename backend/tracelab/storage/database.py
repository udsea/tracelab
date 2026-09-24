import json
import threading
from pathlib import Path
from typing import Any

import duckdb

TABLES = {
    "event_presentations",
    "branch_comparisons",
    "analysis_signals",
    "detector_definitions",
    "artifacts",
    "internal_sources",
    "outline_nodes",
    "analysis_overviews",
    "analysis_inputs",
    "workspaces",
    "experiments",
    "trajectories",
    "events",
    "segments",
    "classifier_definitions",
    "classifier_runs",
    "classifier_results",
    "forks",
    "interventions",
    "annotations",
    "checkpoints",
    "providers",
    "jobs",
    "cache",
    "source_records",
}


class Database:
    """Serialized transactional writes; thread-local read cursors share committed DuckDB data."""

    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.presentation_lock = threading.Lock()
        self.event_revisions: dict[str, int] = {}
        self._local = threading.local()
        self._read_state = threading.Condition()
        self._readers = []
        self._active_reads = 0
        self._closing = False
        self.conn = duckdb.connect(str(path))
        for table in TABLES:
            self.conn.execute(f"""CREATE TABLE IF NOT EXISTS {table} (
                id VARCHAR PRIMARY KEY, workspace_id VARCHAR, experiment_id VARCHAR,
                trajectory_id VARCHAR, classifier_id VARCHAR, event_index INTEGER,
                parent_id VARCHAR, search_text VARCHAR, data JSON NOT NULL
            )""")
        for table, column in [
            ("events", "trajectory_id"),
            ("event_presentations", "trajectory_id"),
            ("analysis_signals", "trajectory_id"),
            ("outline_nodes", "trajectory_id"),
            ("artifacts", "trajectory_id"),
            ("trajectories", "experiment_id"),
            ("experiments", "workspace_id"),
            ("segments", "trajectory_id"),
            ("classifier_results", "trajectory_id"),
            ("classifier_results", "classifier_id"),
            ("annotations", "trajectory_id"),
            ("forks", "trajectory_id"),
            ("trajectories", "parent_id"),
        ]:
            self.conn.execute(
                f"CREATE INDEX IF NOT EXISTS ix_{table}_{column} ON {table}({column})"
            )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_event_order ON events(trajectory_id, event_index)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_presentation_order ON event_presentations(trajectory_id, event_index)"
        )
        self.conn.execute("""CREATE OR REPLACE VIEW current_classifier_results AS
            WITH latest AS (
                SELECT trajectory_id, classifier_id, data->>'runId' AS run_id
                FROM classifier_results
                QUALIFY row_number() OVER (PARTITION BY trajectory_id, classifier_id
                    ORDER BY data->>'createdAt' DESC, id DESC) = 1
            )
            SELECT r.* FROM classifier_results r JOIN latest l
            ON r.trajectory_id = l.trajectory_id AND r.classifier_id = l.classifier_id
            AND (r.data->>'runId') = l.run_id""")

    def _table(self, table):
        if table not in TABLES:
            raise ValueError("Unknown table")
        return table

    def _row(self, data: dict) -> list:
        searchable = " ".join(str(data.get(k) or "") for k in ("content", "tool", "label", "note"))
        return [
            data["id"],
            data.get("workspaceId"),
            data.get("experimentId"),
            data.get("trajectoryId", data.get("sourceTrajectoryId")),
            data.get("classifierId"),
            data.get("index", data.get("startEventIndex")),
            data.get("parentTrajectoryId", data.get("parentId")),
            searchable,
            json.dumps(data, ensure_ascii=False, allow_nan=False),
        ]

    def put(self, table: str, data: Any):
        obj = data.wire() if hasattr(data, "wire") else data
        with self.lock:
            if table == "events":
                self.conn.execute("DELETE FROM event_presentations WHERE id = ?", [obj["id"]])
            self.conn.execute(
                f"INSERT OR REPLACE INTO {self._table(table)} VALUES (?,?,?,?,?,?,?,?,?)",
                self._row(obj),
            )
            if table == "events":
                tid = obj["trajectoryId"]
                self.event_revisions[tid] = self.event_revisions.get(tid, 0) + 1
        return obj

    def put_many(self, table: str, items: list):
        if not items:
            return
        rows = [self._row(x.wire() if hasattr(x, "wire") else x) for x in items]
        with self.lock:
            self.conn.execute("BEGIN")
            try:
                if table == "events":
                    self.conn.executemany(
                        "DELETE FROM event_presentations WHERE id = ?", [[r[0]] for r in rows]
                    )
                self.conn.executemany(
                    f"INSERT OR REPLACE INTO {self._table(table)} VALUES (?,?,?,?,?,?,?,?,?)", rows
                )
                self.conn.execute("COMMIT")
                if table == "events":
                    for tid in {row[3] for row in rows}:
                        self.event_revisions[tid] = self.event_revisions.get(tid, 0) + 1
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise

    def get(self, table: str, id: str) -> dict:
        rows = self.read(f"SELECT data FROM {self._table(table)} WHERE id = ?", [id])
        row = rows[0] if rows else None
        if row is None:
            raise ValueError(f"{table}: {id} not found")
        return json.loads(row[0])

    def maybe(self, table: str, id: str) -> dict | None:
        try:
            return self.get(table, id)
        except ValueError:
            return None

    def read(self, sql: str, args: list | None = None) -> list[tuple]:
        # DuckDB recommends cursor() for independent execution contexts per thread.
        # No writer lock is held while executing/fetching a read.
        with self._read_state:
            if self._closing:
                raise RuntimeError("Database is closing")
            if not hasattr(self._local, "reader"):
                self._local.reader = self.conn.cursor()
                self._readers.append(self._local.reader)
            cursor = self._local.reader
            self._active_reads += 1
        try:
            return cursor.execute(sql, args or []).fetchall()
        finally:
            with self._read_state:
                self._active_reads -= 1
                self._read_state.notify_all()

    def query(self, sql: str, args: list | None = None) -> list[tuple]:
        # Existing internal SELECT callers use the read path. Mutations and
        # transaction commands retain the single serialized writer connection.
        if sql.lstrip().upper().startswith("SELECT "):
            return self.read(sql, args)
        with self.lock:
            return self.conn.execute(sql, args or []).fetchall()

    def list(
        self,
        table: str,
        where: str = "TRUE",
        args: list | None = None,
        limit: int = 10000,
        offset: int = 0,
        order: str = "id",
    ) -> list[dict]:
        rows = self.read(
            f"SELECT data FROM {self._table(table)} WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
            (args or []) + [limit, offset],
        )
        return [json.loads(r[0]) for r in rows]

    def delete(self, table: str, id: str):
        with self.lock:
            if table == "events":
                event = self.maybe("events", id)
                if event:
                    tid = event["trajectoryId"]
                    self.event_revisions[tid] = self.event_revisions.get(tid, 0) + 1
                self.query("DELETE FROM event_presentations WHERE id = ?", [id])
            self.query(f"DELETE FROM {self._table(table)} WHERE id = ?", [id])

    def close(self):
        with self.lock, self._read_state:
            self._closing = True
            self._read_state.wait_for(lambda: self._active_reads == 0)
            for cursor in self._readers:
                cursor.close()
            self._readers.clear()
            self.conn.close()
