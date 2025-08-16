from __future__ import annotations

"""Telegram watcher service using Telethon.

This module provides a :class:`Watcher` which logs in to a Telegram
account, stores the encrypted session in the database and ingests
messages from subscribed channels.  It is intentionally fairly small
and only implements the pieces needed for the unit tests of this kata.
"""

import asyncio
import datetime as dt
import os
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, Optional

try:  # pragma: no cover - telethon may be absent in the execution env
    from telethon import TelegramClient, events, errors
    from telethon.sessions import StringSession
except Exception:  # pragma: no cover
    TelegramClient = None  # type: ignore
    events = None  # type: ignore
    errors = None  # type: ignore
    StringSession = None  # type: ignore

from ..common.crypto import encrypt, decrypt


# ---------------------------------------------------------------------------
# Simhash implementation
# ---------------------------------------------------------------------------

def _compute_simhash(text: str) -> int:
    """Return 64-bit simhash for ``text``.

    The implementation is intentionally small and does not depend on any
    external libraries.  It is based on the standard simhash algorithm
    using word tokens and MD5 for hashing.
    """

    import hashlib

    if not text:
        return 0

    v = [0] * 64
    for token in text.split():
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        for i in range(64):
            if h & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1
    result = 0
    for i, val in enumerate(v):
        if val >= 0:
            result |= 1 << i
    return result


def _hamming(a: int, b: int) -> int:
    """Return Hamming distance between two 64-bit integers."""

    return bin(a ^ b).count("1")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _connect_db(db_url: str) -> sqlite3.Connection:
    """Return a SQLite connection for ``db_url``.

    Only ``sqlite:///`` URLs are supported in the unit tests.  The
    function is synchronous which is good enough for the exercises and we
    keep the API minimal.  Real code would use an async driver.
    """

    if not db_url.startswith("sqlite:///"):
        raise RuntimeError("only sqlite:/// URLs are supported in tests")
    path = db_url[len("sqlite:///") :]
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Watcher service
# ---------------------------------------------------------------------------


@dataclass
class Watcher:
    """High level wrapper around a Telethon client.

    Parameters are read from ``config.load_config`` which merges the
    ``.env`` file, YAML files in ``config/`` and DB settings.  Only a
    subset of settings are required here.
    """

    api_id: int
    api_hash: str
    phone: str
    db_url: str
    secret_key: str
    replay_hours: int = 0

    client: Optional[TelegramClient] = field(init=False, default=None)
    sources: Dict[int, int] = field(init=False, default_factory=dict)

    # -- session ---------------------------------------------------------

    def _load_session(self) -> Optional[str]:
        conn = _connect_db(self.db_url)
        try:
            cur = conn.execute(
                "SELECT enc_session FROM master_sessions WHERE valid=1 ORDER BY id DESC LIMIT 1"
            )
            row = cur.fetchone()
            if not row:
                return None
            token = row[0]
            if isinstance(token, bytes):
                token = token.decode()
            try:
                return decrypt(token, self.secret_key).decode()
            except Exception:
                return None
        finally:
            conn.close()

    def _save_session(self, session: str) -> None:
        enc = encrypt(session.encode(), self.secret_key)
        conn = _connect_db(self.db_url)
        try:
            conn.execute(
                "INSERT INTO master_sessions(enc_session) VALUES (?)", (enc.encode(),)
            )
            conn.commit()
        finally:
            conn.close()

    async def _ensure_client(self) -> TelegramClient:
        if TelegramClient is None:
            raise RuntimeError("Telethon is required to run watcher")

        session = self._load_session()
        if session:
            self.client = TelegramClient(StringSession(session), self.api_id, self.api_hash)
        else:
            self.client = TelegramClient(StringSession(), self.api_id, self.api_hash)
        await self.client.connect()
        if not await self.client.is_user_authorized():
            await self.client.send_code_request(self.phone)
            code = input("Enter code: ")
            try:
                await self.client.sign_in(self.phone, code)
            except errors.SessionPasswordNeededError:
                pwd = input("Password: ")
                await self.client.sign_in(password=pwd)
            session = self.client.session.save()
            self._save_session(session)
        return self.client

    # -- sources ---------------------------------------------------------

    def _refresh_enabled_sources(self) -> None:
        conn = _connect_db(self.db_url)
        try:
            cur = conn.execute("SELECT tg_id, id FROM sources WHERE enabled=1")
            self.sources = {row[0]: row[1] for row in cur.fetchall()}
        finally:
            conn.close()

    async def sync_subscriptions(self) -> None:
        client = await self._ensure_client()
        dialogs = await client.get_dialogs()
        conn = _connect_db(self.db_url)
        try:
            for d in dialogs:
                ent = d.entity
                if getattr(ent, "broadcast", False):  # channel (not group)
                    tg_id = ent.id
                    username = getattr(ent, "username", None)
                    title = ent.title
                    cur = conn.execute(
                        "SELECT id FROM sources WHERE tg_id=?", (tg_id,)
                    )
                    row = cur.fetchone()
                    if row:
                        conn.execute(
                            "UPDATE sources SET username=?, title=? WHERE id=?",
                            (username, title, row[0]),
                        )
                    else:
                        conn.execute(
                            "INSERT INTO sources (tg_id, username, title) VALUES (?, ?, ?)",
                            (tg_id, username, title),
                        )
            conn.commit()
        finally:
            conn.close()
        self._refresh_enabled_sources()

    # -- ingest ----------------------------------------------------------

    def _insert_or_update_post(self, source_id: int, message) -> None:
        text = message.message or ""
        if not text.strip():
            return
        msg_id = message.id
        published_at = message.date
        sim = _compute_simhash(text)
        conn = _connect_db(self.db_url)
        try:
            cur = conn.execute(
                "SELECT id, simhash FROM raw_posts WHERE source_id=? AND tg_message_id=?",
                (source_id, msg_id),
            )
            row = cur.fetchone()
            if row:
                conn.execute(
                    "UPDATE raw_posts SET text=?, simhash=?, status=NULL WHERE id=?",
                    (text, sim, row[0]),
                )
                conn.commit()
                return

            status = None
            window = dt.datetime.utcnow() - dt.timedelta(hours=12)
            cur = conn.execute(
                "SELECT simhash FROM raw_posts WHERE source_id=? AND fetched_at>?",
                (source_id, window),
            )
            for (prev_sim,) in cur.fetchall():
                if prev_sim is None:
                    continue
                if _hamming(sim, prev_sim) <= 3:
                    status = "duplicate"
                    break
            conn.execute(
                """
                INSERT INTO raw_posts
                    (source_id, tg_message_id, text, published_at, simhash, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (source_id, msg_id, text, published_at, sim, status),
            )
            conn.commit()
        finally:
            conn.close()

    async def _on_new(self, event) -> None:
        source_id = self.sources.get(event.chat_id)
        if not source_id:
            return
        self._insert_or_update_post(source_id, event.message)

    async def _on_edit(self, event) -> None:
        source_id = self.sources.get(event.chat_id)
        if not source_id:
            return
        self._insert_or_update_post(source_id, event.message)

    async def _on_delete(self, event) -> None:
        source_id = self.sources.get(event.chat_id)
        if not source_id:
            return
        conn = _connect_db(self.db_url)
        try:
            for msg_id in event.deleted_ids:
                conn.execute(
                    "UPDATE raw_posts SET status='deleted' WHERE source_id=? AND tg_message_id=?",
                    (source_id, msg_id),
                )
            conn.commit()
        finally:
            conn.close()

    async def replay(self) -> None:
        if self.replay_hours <= 0:
            return
        client = await self._ensure_client()
        since = dt.datetime.utcnow() - dt.timedelta(hours=self.replay_hours)
        for tg_id, src_id in self.sources.items():
            async for msg in client.iter_messages(tg_id, offset_date=since, reverse=True):
                self._insert_or_update_post(src_id, msg)

    async def run(self) -> None:
        client = await self._ensure_client()
        await self.sync_subscriptions()
        await self.replay()
        client.add_event_handler(self._on_new, events.NewMessage)
        client.add_event_handler(self._on_edit, events.MessageEdited)
        client.add_event_handler(self._on_delete, events.MessageDeleted)
        await client.run_until_disconnected()


async def main() -> None:
    from ..common.config import load_config

    cfg = load_config()
    watcher = Watcher(
        api_id=int(cfg.get("API_ID", 0)),
        api_hash=cfg.get("API_HASH", ""),
        phone=cfg.get("MASTER_PHONE", ""),
        db_url=cfg.get("DATABASE_URL", "sqlite:///mg.db"),
        secret_key=cfg.get("SECRETS_MASTER_KEY_BASE64", ""),
        replay_hours=int(cfg.get("replay_hours", 0)),
    )
    await watcher.run()


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    asyncio.run(main())
