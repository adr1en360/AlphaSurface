"""
AlphaSurface — Persistent memory store.

SQLite  → local dev   (MEMORY_BACKEND=sqlite, default)
Firestore → Cloud Run  (MEMORY_BACKEND=firestore)

Usage:
    from memory import memory_store
    profile = await memory_store().read(user_id)
    await memory_store().merge(user_id, {"communication_style": "concise"})
"""

import asyncio
import json
import os
import sqlite3
import time
from abc import ABC, abstractmethod


# ── Abstract interface ────────────────────────────────────────────────────────

class MemoryStore(ABC):
    @abstractmethod
    async def read(self, user_id: str) -> dict:
        """Return stored profile dict for user_id, or {} if not found."""
        ...

    @abstractmethod
    async def write(self, user_id: str, data: dict) -> None:
        """Persist data dict for user_id, replacing existing."""
        ...

    async def merge(self, user_id: str, updates: dict) -> dict:
        """Read → deep merge updates → write → return merged result."""
        existing = await self.read(user_id)
        _deep_merge(existing, updates)
        await self.write(user_id, existing)
        return existing


def _deep_merge(base: dict, updates: dict) -> None:
    """In-place deep merge of updates into base."""
    for k, v in updates.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        elif k in base and isinstance(base[k], list) and isinstance(v, list):
            # Append unique items to lists (e.g. observed_traits)
            for item in v:
                if item not in base[k]:
                    base[k].append(item)
        else:
            base[k] = v


# ── SQLite implementation ─────────────────────────────────────────────────────

class SQLiteMemoryStore(MemoryStore):
    def __init__(self, db_path: str = "alphasurface_memory.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id    TEXT PRIMARY KEY,
                data       TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    # ── Sync interface (used by ADK tools which run inside the event loop) ──
    def read_sync(self, user_id: str) -> dict:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT data FROM user_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        conn.close()
        return json.loads(row[0]) if row else {}

    def write_sync(self, user_id: str, data: dict) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO user_profiles (user_id, data, updated_at) VALUES (?, ?, ?)",
            (user_id, json.dumps(data), time.time())
        )
        conn.commit()
        conn.close()

    def merge_sync(self, user_id: str, updates: dict) -> dict:
        existing = self.read_sync(user_id)
        _deep_merge(existing, updates)
        self.write_sync(user_id, existing)
        return existing

    # ── Async interface (used by PersonaAgent and session startup) ──────────
    async def read(self, user_id: str) -> dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.read_sync, user_id)

    async def write(self, user_id: str, data: dict) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.write_sync, user_id, data)


# ── Firestore implementation ──────────────────────────────────────────────────

class FirestoreMemoryStore(MemoryStore):
    def __init__(self):
        from google.cloud import firestore  # type: ignore
        self.db = firestore.AsyncClient()
        self._col = "alphasurface_profiles"

    async def read(self, user_id: str) -> dict:
        doc = await self.db.collection(self._col).document(user_id).get()
        return doc.to_dict() if doc.exists else {}

    async def write(self, user_id: str, data: dict) -> None:
        await self.db.collection(self._col).document(user_id).set(data)


# ── Factory + singleton ───────────────────────────────────────────────────────

_store: MemoryStore | None = None


def memory_store() -> MemoryStore:
    """Returns the module-level MemoryStore singleton."""
    global _store
    if _store is None:
        backend = os.environ.get("MEMORY_BACKEND", "sqlite").lower()
        _store = FirestoreMemoryStore() if backend == "firestore" else SQLiteMemoryStore()
    return _store
