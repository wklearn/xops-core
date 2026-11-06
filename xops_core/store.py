"""Offline SQLite state machine for candidate review and export."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .validators import SCHEMA, ValidationError


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str | Path) -> sqlite3.Connection:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                post_id TEXT NOT NULL UNIQUE,
                account TEXT NOT NULL,
                lang TEXT NOT NULL,
                pillar TEXT NOT NULL,
                evidence_stage TEXT NOT NULL,
                priority TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','approved','rejected','exported')),
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                UNIQUE(account, event_id)
            );
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_row_id INTEGER,
                action TEXT NOT NULL,
                at TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(post_row_id) REFERENCES posts(id)
            );
        """)


def add_posts(conn: sqlite3.Connection, posts: list[dict[str, Any]]) -> dict[str, int]:
    imported = 0
    duplicates = 0
    # Validate the full document BEFORE the database transaction (caller responsibility).
    with conn:
        for item in posts:
            existing_event = conn.execute(
                "SELECT id FROM posts WHERE account=? AND event_id=?",
                (item["account"], item["event_id"]),
            ).fetchone()
            if existing_event:
                duplicates += 1
                continue
            existing_post_id = conn.execute(
                "SELECT id FROM posts WHERE post_id=?", (item["post_id"],)
            ).fetchone()
            if existing_post_id:
                raise ValidationError("post_id is already used by a different event")
            cursor = conn.execute(
                """INSERT INTO posts
                (event_id, post_id, account, lang, pillar, evidence_stage,
                 priority, body, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (item["event_id"], item["post_id"], item["account"],
                 item["lang"], item["pillar"], item["evidence_stage"],
                 item["priority"], json.dumps(item, ensure_ascii=False), timestamp()),
            )
            conn.execute("INSERT INTO audit(post_row_id, action, at) VALUES (?, 'imported', ?)",
                         (cursor.lastrowid, timestamp()))
            imported += 1
    return {"imported": imported, "duplicates": duplicates}


def find_posts(conn: sqlite3.Connection, status: str | None = None, limit: int = 100) -> list[sqlite3.Row]:
    if status:
        return conn.execute("SELECT * FROM posts WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit)).fetchall()
    return conn.execute("SELECT * FROM posts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    result = {s: 0 for s in ("pending", "approved", "rejected", "exported")}
    for row in conn.execute("SELECT status, COUNT(*) n FROM posts GROUP BY status"):
        result[row["status"]] = row["n"]
    return result


def review(conn: sqlite3.Connection, post_row_id: int, decision: str) -> None:
    if decision not in ("approved", "rejected"):
        raise ValidationError("Decision must be approved or rejected")
    with conn:
        row = conn.execute("SELECT status FROM posts WHERE id=?", (post_row_id,)).fetchone()
        if row is None:
            raise ValidationError("Post not found")
        if row["status"] == "exported":
            raise ValidationError("Exported posts cannot be reviewed again")
        if row["status"] == decision:
            return
        cursor = conn.execute(
            "UPDATE posts SET status=?, reviewed_at=? WHERE id=? AND status<>'exported'",
            (decision, timestamp(), post_row_id),
        )
        if cursor.rowcount != 1:
            raise ValidationError("Post review state changed, retry")
        conn.execute("INSERT INTO audit(post_row_id,action,at,detail) VALUES (?,?,?,?)",
                     (post_row_id, "reviewed", timestamp(), decision))


def export_approved(conn: sqlite3.Connection, output: str | Path, keep_approved: bool = False) -> int:
    rows = conn.execute("SELECT id, body FROM posts WHERE status='approved' ORDER BY id").fetchall()
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return 0
    payload = {"version": SCHEMA, "generated_at": timestamp(),
               "posts": [json.loads(row["body"]) for row in rows]}
    # Write to a temporary file and replace only when the JSON is complete.
    temp = path.with_name(path.name + ".tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    if not keep_approved:
        with conn:
            for row in rows:
                updated = conn.execute(
                    "UPDATE posts SET status='exported' WHERE id=? AND status='approved'",
                    (row["id"],),
                )
                if updated.rowcount:
                    conn.execute("INSERT INTO audit(post_row_id,action,at,detail) VALUES (?,?,?,?)",
                                 (row["id"], "exported", timestamp(), str(path)))
    return len(rows)
