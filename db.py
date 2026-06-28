import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "provenance.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                content_id   TEXT PRIMARY KEY,
                creator_id   TEXT NOT NULL,
                timestamp    TEXT NOT NULL,
                llm_score    REAL,
                stylo_score  REAL,
                combined     REAL,
                confidence   REAL,
                attribution  TEXT,
                label_variant TEXT,
                label        TEXT,
                status       TEXT DEFAULT 'classified',
                appeals      TEXT DEFAULT '[]'
            )
        """)
        conn.commit()


def insert_decision(record: dict):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO decisions
              (content_id, creator_id, timestamp, llm_score, stylo_score,
               combined, confidence, attribution, label_variant, label, status, appeals)
            VALUES
              (:content_id, :creator_id, :timestamp, :llm_score, :stylo_score,
               :combined, :confidence, :attribution, :label_variant, :label, :status, :appeals)
        """, {**record, "appeals": json.dumps(record.get("appeals", []))})
        conn.commit()


def get_decision(content_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM decisions WHERE content_id = ?", (content_id,)
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["appeals"] = json.loads(d["appeals"])
    return d


def update_decision(content_id: str, updates: dict):
    if "appeals" in updates:
        updates["appeals"] = json.dumps(updates["appeals"])
    sets = ", ".join(f"{k} = :{k}" for k in updates)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE decisions SET {sets} WHERE content_id = :content_id",
            {**updates, "content_id": content_id},
        )
        conn.commit()


def get_log(limit: int = 20, offset: int = 0):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM decisions ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    entries = []
    for row in rows:
        d = dict(row)
        d["appeals"] = json.loads(d["appeals"])
        entries.append(d)
    return entries, total
