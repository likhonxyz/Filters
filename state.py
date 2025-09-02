# state.py
from __future__ import annotations
from collections.abc import MutableMapping
from typing import Any, Dict

from db import (
    init_db,
    load_group, save_group, load_all_groups,
    set_user_group, get_user_groups, get_all_user_groups,
    # ⬇️ PM target persist helpers
    set_pm_target as db_set_pm_target,
    get_pm_target as db_get_pm_target,
    clear_pm_target as db_clear_pm_target,
)

# Initialize DB at import
init_db()

# ---------- In-memory ephemeral states ----------
PENDING_INPUT: Dict[int, dict] = {}      # per-user pending prompts
LAST_WELCOME_MSG: Dict[int, int] = {}    # chat_id -> last message_id
WELCOMED_ONCE: Dict[int, set] = {}       # chat_id -> set(user_id)

# ---------- Persistent wrappers ----------

class _GroupSettings(MutableMapping):
    """
    chat_id -> dict persisted in SQLite 'groups' as JSON
    - __getitem__ lazy-loads from DB if not cached
    - __setitem__ immediately writes to DB
    """
    def __init__(self):
        self._cache: Dict[int, dict] = load_all_groups()

    def __getitem__(self, gid: int) -> dict:
        gid = int(gid)
        if gid in self._cache:
            return self._cache[gid]
        data = load_group(gid) or {}
        self._cache[gid] = data
        return data

    def __setitem__(self, gid: int, value: dict) -> None:
        gid = int(gid)
        if not isinstance(value, dict):
            raise TypeError("GROUP_SETTINGS value must be dict")
        self._cache[gid] = value
        save_group(gid, value)

    def __delitem__(self, gid: int) -> None:
        gid = int(gid)
        if gid in self._cache:
            del self._cache[gid]
        # (optional) delete from DB if you add such an op

    def __iter__(self):
        return iter(self._cache)

    def __len__(self) -> int:
        return len(self._cache)

GROUP_SETTINGS = _GroupSettings()

class _UserGroups(MutableMapping):
    """
    user_id -> { gid: { 'title': str } }
    Backed by 'user_groups' table.
    """
    def __init__(self):
        self._cache: Dict[int, Dict[int, dict]] = get_all_user_groups()

    def __getitem__(self, user_id: int) -> Dict[int, dict]:
        user_id = int(user_id)
        if user_id in self._cache:
            return self._cache[user_id]
        data = get_user_groups(user_id)
        self._cache[user_id] = data
        return data

    def __setitem__(self, user_id: int, value: Dict[int, dict]) -> None:
        # Bulk set (cache only)
        self._cache[int(user_id)] = value

    def __delitem__(self, user_id: int) -> None:
        user_id = int(user_id)
        if user_id in self._cache:
            del self._cache[user_id]

    def __iter__(self):
        return iter(self._cache)

    def __len__(self) -> int:
        return len(self._cache)

    # Persist a single mapping
    def connect(self, user_id: int, gid: int, title: str = ""):
        set_user_group(int(user_id), int(gid), title or "")
        # refresh cache row
        self._cache[int(user_id)] = get_user_groups(int(user_id))

USER_GROUPS = _UserGroups()

# ---------- PM target helpers (persisted in DB) ----------

def set_pm_target(user_id: int, gid: int) -> None:
    """
    Save user's selected group (used by /filters_group).
    """
    db_set_pm_target(int(user_id), int(gid))

def get_pm_target(user_id: int) -> int | None:
    """
    Load user's last-selected group for PM filter commands.
    """
    try:
        return db_get_pm_target(int(user_id))
    except Exception:
        return None

def clear_pm_target(user_id: int) -> None:
    """
    Optional: clear stored PM target (e.g., if user unlinks groups).
    """
    try:
        db_clear_pm_target(int(user_id))
    except Exception:
        pass

def ensure_pm_target(user_id: int) -> int | None:
    """
    Convenience: if user has exactly one linked group, auto-select it
    and persist; else return whatever is stored via set_pm_target().
    """
    groups = USER_GROUPS[int(user_id)]
    if groups and len(groups) == 1:
        only_gid = next(iter(groups.keys()))
        db_set_pm_target(int(user_id), int(only_gid))
        return int(only_gid)
    return get_pm_target(int(user_id))