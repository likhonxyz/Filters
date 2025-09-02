# db.py
import os
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

# ---- DB path (persistent) ----
# Prefer explicit env var; else create ./data/bot.sqlite3 next to this file
APP_ROOT = Path(__file__).resolve().parent
DATA_DIR = os.environ.get("BOT_DATA_DIR") or str(APP_ROOT / "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = str(Path(DATA_DIR) / "bot.sqlite3")

@contextmanager
def conn_ctx():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        con.row_factory = sqlite3.Row
        yield con
    finally:
        con.commit()
        con.close()

def init_db():
    with conn_ctx() as con:
        cur = con.cursor()
        # groups: per chat (gid) JSON blob for settings etc.
        cur.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            gid     INTEGER PRIMARY KEY,
            data    TEXT NOT NULL
        )
        """)
        # user_groups: which user is connected to which group, store title
        cur.execute("""
        CREATE TABLE IF NOT EXISTS user_groups (
            user_id INTEGER NOT NULL,
            gid     INTEGER NOT NULL,
            title   TEXT,
            PRIMARY KEY (user_id, gid)
        )
        """)
        # pm_targets: user's last-selected group for PM filter management
        cur.execute("""
        CREATE TABLE IF NOT EXISTS pm_targets (
            user_id INTEGER PRIMARY KEY,
            group_id INTEGER NOT NULL
        )
        """)
        con.commit()

# ---------- groups table ops ----------
def load_group(gid: int) -> dict | None:
    with conn_ctx() as con:
        cur = con.cursor()
        cur.execute("SELECT data FROM groups WHERE gid = ?", (gid,))
        row = cur.fetchone()
        if not row:
            return None
        try:
            return json.loads(row["data"])
        except Exception:
            return None

def save_group(gid: int, data: dict):
    payload = json.dumps(data or {}, ensure_ascii=False, separators=(",", ":"))
    with conn_ctx() as con:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO groups(gid, data) VALUES(?, ?) "
            "ON CONFLICT(gid) DO UPDATE SET data=excluded.data",
            (gid, payload)
        )
        con.commit()

def load_all_groups() -> dict[int, dict]:
    out: dict[int, dict] = {}
    with conn_ctx() as con:
        cur = con.cursor()
        cur.execute("SELECT gid, data FROM groups")
        for gid, data in cur.fetchall():
            try:
                out[int(gid)] = json.loads(data)
            except Exception:
                out[int(gid)] = {}
    return out

# ---------- user_groups table ops ----------
def set_user_group(user_id: int, gid: int, title: str = ""):
    with conn_ctx() as con:
        con.execute(
            "INSERT INTO user_groups(user_id, gid, title) VALUES(?, ?, ?) "
            "ON CONFLICT(user_id, gid) DO UPDATE SET title=excluded.title",
            (user_id, gid, title or "")
        )
        con.commit()

def remove_user_group(user_id: int, gid: int):
    with conn_ctx() as con:
        con.execute("DELETE FROM user_groups WHERE user_id = ? AND gid = ?", (user_id, gid))
        con.commit()

def get_user_groups(user_id: int) -> dict[int, dict]:
    """
    Returns { gid: { 'title': str } }
    """
    with conn_ctx() as con:
        cur = con.cursor()
        cur.execute("SELECT gid, title FROM user_groups WHERE user_id = ?", (user_id,))
        res = {}
        for gid, title in cur.fetchall():
            res[int(gid)] = {"title": title or ""}
        return res

def get_all_user_groups() -> dict[int, dict[int, dict]]:
    """
    Returns { user_id: { gid: { 'title': str } } }
    """
    out: dict[int, dict[int, dict]] = {}
    with conn_ctx() as con:
        cur = con.cursor()
        cur.execute("SELECT user_id, gid, title FROM user_groups")
        for uid, gid, title in cur.fetchall():
            uid = int(uid); gid = int(gid)
            out.setdefault(uid, {})[gid] = {"title": title or ""}
    return out

# ---------- pm_targets table ops (persist /filters_group selection) ----------
def set_pm_target(user_id: int, group_id: int):
    """Persist the user's selected target group for PM filter commands."""
    with conn_ctx() as con:
        con.execute(
            "INSERT INTO pm_targets(user_id, group_id) VALUES(?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET group_id=excluded.group_id",
            (user_id, group_id)
        )
        con.commit()

def get_pm_target(user_id: int) -> int | None:
    """Return last selected group_id for this user, or None."""
    with conn_ctx() as con:
        cur = con.cursor()
        cur.execute("SELECT group_id FROM pm_targets WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return int(row["group_id"]) if row else None

def clear_pm_target(user_id: int):
    """Clear stored PM target for a user (optional helper)."""
    with conn_ctx() as con:
        con.execute("DELETE FROM pm_targets WHERE user_id = ?", (user_id,))
        con.commit()