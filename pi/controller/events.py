"""Events: SQLite store `robot.db`, replayed on SYNC (K09, design 4.5)."""
from __future__ import annotations

import itertools
import json
import logging
import sqlite3
import time

from common import protocol as P

log = logging.getLogger("kashimo.events")
POSE_KEYS = ("s", "x", "y", "slab", "pan", "tilt")


class EventStore:
    """Every event gets an id that only grows, also across restarts. A failing disk never loses a live event."""

    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, ts REAL NOT NULL, kind TEXT NOT NULL,"
                        " pose TEXT NOT NULL, data TEXT NOT NULL)")
        self.db.commit()
        self._next = (self.db.execute("SELECT MAX(id) FROM events").fetchone()[0] or 0) + 1
        self._ram: list[tuple] = []  # rows the disk refused, kept so SYNC still finds them
        self._seq = itertools.count(1)

    @property
    def last_id(self) -> int:
        return self._next - 1

    def add(self, kind: str, pose: dict, data: dict | None = None) -> P.Event:
        """Validate, store and return the event. Raises ProtocolError for a bad kind, pose or data."""
        ev = P.Event(seq=next(self._seq), ts=time.time(), id=self._next, kind=kind, data=dict(data or {}),
                     **{k: pose[k] for k in POSE_KEYS})
        P.encode(ev)  # refuse what decode would refuse (ALERT_DEFECT fields included)
        row = (ev.id, ev.ts, kind, json.dumps({k: pose[k] for k in POSE_KEYS}), json.dumps(ev.data))
        try:
            self.db.execute("INSERT INTO events VALUES (?,?,?,?,?)", row)
            self.db.commit()
        except sqlite3.Error:
            log.exception("event %s not written to disk, kept in RAM", ev.id)
            self._ram.append(row)
        self._next += 1
        return ev

    def since(self, since_id: int) -> list[P.Event]:
        """Events with an id above since_id, oldest first (fresh seq numbers, original timestamps)."""
        try:
            rows = self.db.execute("SELECT id, ts, kind, pose, data FROM events WHERE id > ? ORDER BY id", (since_id,)).fetchall()
        except sqlite3.Error:
            log.exception("cannot read events from disk")
            rows = []
        rows = sorted({r[0]: r for r in rows + [r for r in self._ram if r[0] > since_id]}.values())
        return [P.Event(seq=next(self._seq), ts=ts, id=i, kind=k, data=json.loads(d), **json.loads(p))
                for i, ts, k, p, d in rows]

    def close(self) -> None:
        try:
            self.db.close()
        except sqlite3.Error:
            pass
