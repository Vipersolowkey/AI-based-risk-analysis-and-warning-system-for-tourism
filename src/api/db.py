# src/api/db.py
"""
Raw sqlite3 storage for users, trip history, and push subscriptions.
No ORM, matching the repo's existing sqlite usage in data/state/seen_ids.sqlite.
"""
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

from src.api.config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trip_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    destination TEXT NOT NULL,
    lat REAL,
    lon REAL,
    trip_purpose TEXT,
    risk_score INTEGER,
    weather_risk_score REAL,
    recommendation TEXT,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_trip_history_user ON trip_history(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint TEXT UNIQUE NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    watched_destination TEXT,
    watched_lat REAL,
    watched_lon REAL,
    last_alert_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(_SCHEMA)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(push_subscriptions)")}
        if "last_alert_at" not in columns:
            conn.execute("ALTER TABLE push_subscriptions ADD COLUMN last_alert_at TEXT")
        conn.commit()
    finally:
        conn.close()


# ============================================================
# USERS
# ============================================================
def create_user(email: str, password_hash: str) -> Dict[str, Any]:
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email, password_hash),
        )
        conn.commit()
        return get_user_by_id(cur.lastrowid)
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ============================================================
# TRIP HISTORY
# ============================================================
def save_trip_history(
    user_id: int,
    destination: str,
    lat: Optional[float],
    lon: Optional[float],
    trip_purpose: Optional[str],
    result: Dict[str, Any],
) -> None:
    risk_score = (result.get("risk") or {}).get("risk_score")
    weather = result.get("weather") or {}
    weather_risk_score = weather.get("adjusted_risk_score", weather.get("risk_score"))
    recommendation = result.get("recommendation")
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO trip_history
               (user_id, destination, lat, lon, trip_purpose, risk_score,
                weather_risk_score, recommendation, result_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id, destination, lat, lon, trip_purpose, risk_score,
                weather_risk_score, recommendation, json.dumps(result, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_trip_history(user_id: int, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT id, destination, lat, lon, trip_purpose, risk_score,
                      weather_risk_score, recommendation, created_at
               FROM trip_history WHERE user_id = ?
               ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            (user_id, limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_trip_history_row(trip_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM trip_history WHERE id = ? AND user_id = ?", (trip_id, user_id)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_trip_history(trip_id: int, user_id: int) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM trip_history WHERE id = ? AND user_id = ?", (trip_id, user_id)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ============================================================
# PUSH SUBSCRIPTIONS
# ============================================================
def save_push_subscription(
    user_id: int,
    endpoint: str,
    p256dh: str,
    auth: str,
    watched_destination: Optional[str] = None,
    watched_lat: Optional[float] = None,
    watched_lon: Optional[float] = None,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO push_subscriptions
               (user_id, endpoint, p256dh, auth, watched_destination, watched_lat, watched_lon)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(endpoint) DO UPDATE SET
                 user_id=excluded.user_id,
                 p256dh=excluded.p256dh, auth=excluded.auth,
                 last_alert_at=CASE
                   WHEN push_subscriptions.user_id != excluded.user_id
                     OR push_subscriptions.watched_lat IS NOT excluded.watched_lat
                     OR push_subscriptions.watched_lon IS NOT excluded.watched_lon
                   THEN NULL ELSE push_subscriptions.last_alert_at END,
                 watched_destination=excluded.watched_destination,
                 watched_lat=excluded.watched_lat, watched_lon=excluded.watched_lon""",
            (user_id, endpoint, p256dh, auth, watched_destination, watched_lat, watched_lon),
        )
        conn.commit()
    finally:
        conn.close()


def delete_push_subscription(user_id: int, endpoint: str) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?", (user_id, endpoint))
        conn.commit()
    finally:
        conn.close()


def list_push_subscriptions_for_user(user_id: int) -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM push_subscriptions WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_push_alert_sent(user_id: int, endpoint: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE push_subscriptions SET last_alert_at = datetime('now') WHERE user_id = ? AND endpoint = ?",
            (user_id, endpoint),
        )
        conn.commit()
    finally:
        conn.close()


def clear_push_alert_sent(user_id: int, endpoint: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE push_subscriptions SET last_alert_at = NULL WHERE user_id = ? AND endpoint = ?",
            (user_id, endpoint),
        )
        conn.commit()
    finally:
        conn.close()


def list_all_push_subscriptions() -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM push_subscriptions").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
