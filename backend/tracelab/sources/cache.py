"""Disposable byte cache, separate from the research DuckDB. Pinned entries resist LRU eviction."""

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path


def key(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def source_key(ref):
    return key([ref.kind, ref.uri, ref.revision, ref.etag, ref.checksum])


class RemoteCache:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / "index.sqlite", check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS entries (key TEXT PRIMARY KEY, source TEXT, category TEXT, size INTEGER, accessed REAL, pinned INTEGER DEFAULT 0)"
        )
        self.db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        self.db.execute("CREATE INDEX IF NOT EXISTS entry_source ON entries(source)")
        self.db.commit()
        self.transferred_bytes = 0
        self.requests = 0

    def path(self, category, id):
        return self.root / category / id

    def get_path(self, category, id):
        with self.lock:
            path = self.path(category, id)
            if path.is_file():
                self.db.execute("UPDATE entries SET accessed=? WHERE key=?", (time.time(), id))
                self.db.commit()
                return path
        return None

    def get(self, category, id):
        with self.lock:
            path = self.get_path(category, id)
            return path.read_bytes() if path else None

    def put(self, category, id, value, source="", pinned=False):
        with self.lock:
            path = self.path(category, id)
            path.parent.mkdir(exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(value)
            temporary.replace(path)
            self.db.execute(
                "INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?,?)",
                (id, source, category, len(value), time.time(), int(pinned)),
            )
            self.db.commit()
            self.evict()
        return path

    def maximum(self):
        row = self.db.execute("SELECT value FROM settings WHERE key='maximum'").fetchone()
        return int(row[0]) if row else 20 * 1024**3

    def configure(self, maximum):
        if not 16 * 1024**2 <= maximum <= 10 * 1024**4:
            raise ValueError("Cache size must be between 16 MiB and 10 TiB")
        with self.lock:
            self.db.execute(
                "INSERT OR REPLACE INTO settings VALUES ('maximum',?)", (str(int(maximum)),)
            )
            self.db.commit()
            self.evict()
        return self.stats()

    def stats(self, source=None):
        with self.lock:
            where, args = (" WHERE source=?", [source]) if source else ("", [])
            rows = self.db.execute(
                "SELECT category,SUM(size),SUM(CASE WHEN pinned THEN size ELSE 0 END) FROM entries"
                + where
                + " GROUP BY category",
                args,
            ).fetchall()
            return {
                "usageBytes": sum(r[1] for r in rows),
                "pinnedBytes": sum(r[2] for r in rows),
                "maximumBytes": self.maximum(),
                "categories": {r[0]: r[1] for r in rows},
                "transferredBytes": self.transferred_bytes,
                "requests": self.requests,
            }

    def clear(self, source=None, include_pinned=False):
        with self.lock:
            clauses, args = (["source=?"], [source]) if source else (["1=1"], [])
            if not include_pinned:
                clauses.append("pinned=0")
            for id, category in self.db.execute(
                "SELECT key,category FROM entries WHERE " + " AND ".join(clauses), args
            ).fetchall():
                self.path(category, id).unlink(missing_ok=True)
                self.db.execute("DELETE FROM entries WHERE key=?", (id,))
            self.db.commit()
        return self.stats(source)

    def evict(self):
        total = self.db.execute("SELECT COALESCE(SUM(size),0) FROM entries").fetchone()[0]
        for id, category, size in self.db.execute(
            "SELECT key,category,size FROM entries WHERE pinned=0 ORDER BY accessed"
        ).fetchall():
            if total <= self.maximum():
                break
            self.path(category, id).unlink(missing_ok=True)
            self.db.execute("DELETE FROM entries WHERE key=?", (id,))
            total -= size
        self.db.commit()

    def close(self):
        self.db.close()
