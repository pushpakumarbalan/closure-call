"""Append-only decision record. What was known, when, and what was decided - reconstructable after the fact.

SQLite, insert-only, with a SHA-256 hash chain so any edit to history is detectable.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import uuid
from contextlib import contextmanager

import httpx

from . import config
from .models import DecisionRecord, NotificationPackage, Posture, Recommendation, now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  id TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  facility_id TEXT NOT NULL,
  facility_name TEXT NOT NULL,
  recommended_posture TEXT NOT NULL,
  decided_posture TEXT NOT NULL,
  decided_by TEXT NOT NULL,
  override INTEGER NOT NULL,
  override_reason TEXT,
  recommendation_json TEXT NOT NULL,
  notification_json TEXT,
  prev_hash TEXT,
  hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS decisions_no_update BEFORE UPDATE ON decisions BEGIN SELECT RAISE(ABORT, 'decision records are append-only'); END;
CREATE TRIGGER IF NOT EXISTS decisions_no_delete BEFORE DELETE ON decisions BEGIN SELECT RAISE(ABORT, 'decision records are append-only'); END;
CREATE TABLE IF NOT EXISTS embeddings (
  record_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  facility_name TEXT NOT NULL,
  posture TEXT NOT NULL,
  text TEXT NOT NULL,
  vector TEXT NOT NULL
);
"""


@contextmanager
def _conn():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        c.executescript(SCHEMA)
        yield c
        c.commit()
    finally:
        c.close()


def _hash(payload: dict, prev: str | None) -> str:
    return hashlib.sha256((prev or "") .encode() + json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def append(rec: Recommendation, decided_posture: Posture, decided_by: str, override_reason: str | None, notification: NotificationPackage | None) -> DecisionRecord:
    with _conn() as c:
        last = c.execute("SELECT hash FROM decisions ORDER BY seq DESC LIMIT 1").fetchone()
        prev = last["hash"] if last else None
        rid = uuid.uuid4().hex[:12]
        created = now_iso()
        rec_json = rec.model_dump(mode="json")
        not_json = notification.model_dump(mode="json") if notification else None
        override = decided_posture != rec.posture
        payload = {"id": rid, "created_at": created, "facility_id": rec.facility_id, "recommended": rec.posture.value, "decided": decided_posture.value,
                   "decided_by": decided_by, "override_reason": override_reason, "recommendation": rec_json, "notification": not_json}
        h = _hash(payload, prev)
        cur = c.execute(
            "INSERT INTO decisions (id, created_at, facility_id, facility_name, recommended_posture, decided_posture, decided_by, override, override_reason, recommendation_json, notification_json, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, created, rec.facility_id, rec.facility_name, rec.posture.value, decided_posture.value, decided_by, int(override), override_reason,
             json.dumps(rec_json), json.dumps(not_json) if not_json else None, prev, h),
        )
        record = DecisionRecord(id=rid, seq=cur.lastrowid, created_at=created, facility_id=rec.facility_id, facility_name=rec.facility_name,
                                recommended_posture=rec.posture, decided_posture=decided_posture, decided_by=decided_by, override=override,
                                override_reason=override_reason, recommendation=rec, notification=notification, prev_hash=prev, hash=h)
    remember(record)
    return record


def _embed(text: str) -> list[float] | None:
    if not config.LLM_ENABLED:
        return None
    try:
        r = httpx.post(f"{config.LLM_BASE_URL}/embeddings", headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
                       json={"model": os_embed_model(), "input": text[:2000]}, timeout=20)
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]
    except Exception:
        return None


def os_embed_model() -> str:
    import os
    return os.getenv("LLM_EMBEDDING_MODEL_ID", "hackathon-embedding")


def remember(record: DecisionRecord) -> None:
    vec = _embed(f"{record.facility_name}. {record.decided_posture.value}. {record.recommendation.rationale}")
    if not vec:
        return
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO embeddings (record_id, created_at, facility_name, posture, text, vector) VALUES (?,?,?,?,?,?)",
                  (record.id, record.created_at, record.facility_name, record.decided_posture.value, record.recommendation.rationale[:500], json.dumps(vec)))


def recall(text: str, k: int = 3) -> list[dict]:
    """Nearest past decisions by cosine similarity on Akamai's embedding model."""
    query = _embed(text)
    if not query:
        return []
    with _conn() as c:
        rows = c.execute("SELECT record_id, created_at, facility_name, posture, text, vector FROM embeddings").fetchall()
    scored = []
    qn = math.sqrt(sum(x * x for x in query)) or 1
    for row in rows:
        vec = json.loads(row["vector"])
        vn = math.sqrt(sum(x * x for x in vec)) or 1
        score = sum(a * b for a, b in zip(query, vec)) / (qn * vn)
        scored.append({"record_id": row["record_id"], "created_at": row["created_at"], "facility_name": row["facility_name"],
                       "posture": row["posture"], "text": row["text"], "score": round(score, 3)})
    scored.sort(key=lambda s: -s["score"])
    return scored[:k]


def _row_to_record(r: sqlite3.Row) -> DecisionRecord:
    return DecisionRecord(
        id=r["id"], seq=r["seq"], created_at=r["created_at"], facility_id=r["facility_id"], facility_name=r["facility_name"],
        recommended_posture=Posture(r["recommended_posture"]), decided_posture=Posture(r["decided_posture"]), decided_by=r["decided_by"],
        override=bool(r["override"]), override_reason=r["override_reason"],
        recommendation=Recommendation.model_validate(json.loads(r["recommendation_json"])),
        notification=NotificationPackage.model_validate(json.loads(r["notification_json"])) if r["notification_json"] else None,
        prev_hash=r["prev_hash"], hash=r["hash"],
    )


def list_records(facility_id: str | None = None, limit: int = 50) -> list[dict]:
    with _conn() as c:
        q = "SELECT seq, id, created_at, facility_id, facility_name, recommended_posture, decided_posture, decided_by, override, override_reason, prev_hash, hash FROM decisions"
        args: tuple = ()
        if facility_id:
            q += " WHERE facility_id = ?"
            args = (facility_id,)
        q += " ORDER BY seq DESC LIMIT ?"
        rows = c.execute(q, args + (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_record(rid: str) -> DecisionRecord | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM decisions WHERE id = ?", (rid,)).fetchone()
        return _row_to_record(r) if r else None


def verify_chain() -> dict:
    """Recompute the hash chain; returns the first break if any."""
    with _conn() as c:
        rows = c.execute("SELECT * FROM decisions ORDER BY seq ASC").fetchall()
    prev = None
    for r in rows:
        payload = {"id": r["id"], "created_at": r["created_at"], "facility_id": r["facility_id"], "recommended": r["recommended_posture"],
                   "decided": r["decided_posture"], "decided_by": r["decided_by"], "override_reason": r["override_reason"],
                   "recommendation": json.loads(r["recommendation_json"]), "notification": json.loads(r["notification_json"]) if r["notification_json"] else None}
        if r["prev_hash"] != prev or _hash(payload, prev) != r["hash"]:
            return {"ok": False, "count": len(rows), "first_break_seq": r["seq"]}
        prev = r["hash"]
    return {"ok": True, "count": len(rows), "head": prev}
