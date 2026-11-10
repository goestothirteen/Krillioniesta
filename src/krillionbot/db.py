"""SQLite store. One row per person per dive; everything else is derived."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id     INTEGER PRIMARY KEY,
    title       TEXT,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS players (
    chat_id     INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    name        TEXT NOT NULL,
    username    TEXT,
    PRIMARY KEY (chat_id, user_id)
);
CREATE TABLE IF NOT EXISTS results (
    chat_id     INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    dive        INTEGER NOT NULL,
    score       INTEGER NOT NULL,
    tiers       TEXT NOT NULL,
    posted_at   TEXT NOT NULL,
    PRIMARY KEY (chat_id, user_id, dive)
);
CREATE INDEX IF NOT EXISTS results_chat_dive ON results (chat_id, dive);
CREATE TABLE IF NOT EXISTS forfeits (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    text        TEXT NOT NULL,
    added_by    INTEGER,
    used_week   TEXT
);
CREATE TABLE IF NOT EXISTS posted (
    chat_id     INTEGER NOT NULL,
    kind        TEXT NOT NULL,   -- 'daily' | 'weekly' | 'nudge'
    key         TEXT NOT NULL,   -- dive number or week monday
    PRIMARY KEY (chat_id, kind, key)
);
"""


@dataclass(frozen=True, slots=True)
class Player:
    user_id: int
    name: str
    username: str | None = None


@dataclass(frozen=True, slots=True)
class Result:
    user_id: int
    dive: int
    score: int
    tiers: str
    posted_at: datetime


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


class Store:
    def __init__(self, path: str) -> None:
        self.path = path
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        if self.path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None, "Store not opened"
        return self._db

    # -- chats & players -------------------------------------------------

    async def ensure_chat(self, chat_id: int, title: str | None) -> None:
        await self.db.execute(
            "INSERT INTO chats (chat_id, title, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title",
            (chat_id, title, _now()),
        )
        await self.db.commit()

    async def chat_ids(self) -> list[int]:
        cur = await self.db.execute("SELECT chat_id FROM chats")
        return [r[0] for r in await cur.fetchall()]

    async def forget_chat(self, chat_id: int) -> None:
        await self.db.execute("DELETE FROM chats WHERE chat_id=?", (chat_id,))
        await self.db.commit()

    async def upsert_player(self, chat_id: int, player: Player) -> None:
        await self.db.execute(
            "INSERT INTO players (chat_id, user_id, name, username) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(chat_id, user_id) DO UPDATE SET name=excluded.name, username=excluded.username",
            (chat_id, player.user_id, player.name, player.username),
        )
        await self.db.commit()

    async def players(self, chat_id: int) -> dict[int, Player]:
        cur = await self.db.execute(
            "SELECT user_id, name, username FROM players WHERE chat_id=?", (chat_id,)
        )
        return {r["user_id"]: Player(r["user_id"], r["name"], r["username"]) for r in await cur.fetchall()}

    # -- results -----------------------------------------------------------

    async def add_result(self, chat_id: int, user_id: int, dive: int, score: int, tiers: str) -> bool:
        """Store a result. Returns False if this person already has one for the dive."""
        cur = await self.db.execute(
            "INSERT OR IGNORE INTO results (chat_id, user_id, dive, score, tiers, posted_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, user_id, dive, score, tiers, _now()),
        )
        await self.db.commit()
        return cur.rowcount == 1

    async def get_result(self, chat_id: int, user_id: int, dive: int) -> Result | None:
        cur = await self.db.execute(
            "SELECT user_id, dive, score, tiers, posted_at FROM results "
            "WHERE chat_id=? AND user_id=? AND dive=?",
            (chat_id, user_id, dive),
        )
        row = await cur.fetchone()
        return self._result(row) if row else None

    async def results_for_dive(self, chat_id: int, dive: int) -> list[Result]:
        cur = await self.db.execute(
            "SELECT user_id, dive, score, tiers, posted_at FROM results WHERE chat_id=? AND dive=? "
            "ORDER BY score DESC, posted_at ASC",
            (chat_id, dive),
        )
        return [self._result(r) for r in await cur.fetchall()]

    async def results_for_dives(self, chat_id: int, dives: list[int]) -> list[Result]:
        if not dives:
            return []
        marks = ",".join("?" * len(dives))
        cur = await self.db.execute(
            f"SELECT user_id, dive, score, tiers, posted_at FROM results "
            f"WHERE chat_id=? AND dive IN ({marks}) ORDER BY dive, score DESC, posted_at ASC",
            (chat_id, *dives),
        )
        return [self._result(r) for r in await cur.fetchall()]

    async def all_results(self, chat_id: int) -> list[Result]:
        cur = await self.db.execute(
            "SELECT user_id, dive, score, tiers, posted_at FROM results WHERE chat_id=? ORDER BY dive",
            (chat_id,),
        )
        return [self._result(r) for r in await cur.fetchall()]

    async def user_results(self, chat_id: int, user_id: int) -> list[Result]:
        cur = await self.db.execute(
            "SELECT user_id, dive, score, tiers, posted_at FROM results "
            "WHERE chat_id=? AND user_id=? ORDER BY dive",
            (chat_id, user_id),
        )
        return [self._result(r) for r in await cur.fetchall()]

    async def latest_result(self, chat_id: int, user_id: int) -> Result | None:
        """The result this person posted most recently (by time, not dive number)."""
        cur = await self.db.execute(
            "SELECT user_id, dive, score, tiers, posted_at FROM results "
            "WHERE chat_id=? AND user_id=? ORDER BY posted_at DESC LIMIT 1",
            (chat_id, user_id),
        )
        row = await cur.fetchone()
        return self._result(row) if row else None

    async def delete_result(self, chat_id: int, user_id: int, dive: int) -> bool:
        cur = await self.db.execute(
            "DELETE FROM results WHERE chat_id=? AND user_id=? AND dive=?", (chat_id, user_id, dive)
        )
        await self.db.commit()
        return cur.rowcount == 1

    async def clear_dive(self, chat_id: int, dive: int) -> int:
        """Wipe everyone's results for one dive (and let its wrap post again)."""
        cur = await self.db.execute("DELETE FROM results WHERE chat_id=? AND dive=?", (chat_id, dive))
        await self.db.execute(
            "DELETE FROM posted WHERE chat_id=? AND kind IN ('daily','nudge') AND key=?", (chat_id, str(dive))
        )
        await self.db.commit()
        return cur.rowcount

    async def clear_chat(self, chat_id: int) -> int:
        """Wipe every result, forfeit and post marker for a chat. Players are kept."""
        cur = await self.db.execute("DELETE FROM results WHERE chat_id=?", (chat_id,))
        await self.db.execute("DELETE FROM forfeits WHERE chat_id=?", (chat_id,))
        await self.db.execute("DELETE FROM posted WHERE chat_id=?", (chat_id,))
        await self.db.commit()
        return cur.rowcount

    @staticmethod
    def _result(r: aiosqlite.Row) -> Result:
        return Result(r["user_id"], r["dive"], r["score"], r["tiers"], _dt(r["posted_at"]))

    # -- forfeits ----------------------------------------------------------

    async def add_forfeit(self, chat_id: int, text: str, added_by: int | None) -> None:
        await self.db.execute(
            "INSERT INTO forfeits (chat_id, text, added_by) VALUES (?, ?, ?)", (chat_id, text, added_by)
        )
        await self.db.commit()

    async def forfeits(self, chat_id: int) -> list[tuple[int, str, str | None]]:
        cur = await self.db.execute(
            "SELECT id, text, used_week FROM forfeits WHERE chat_id=? ORDER BY id", (chat_id,)
        )
        return [(r["id"], r["text"], r["used_week"]) for r in await cur.fetchall()]

    async def remove_forfeit(self, chat_id: int, forfeit_id: int) -> bool:
        cur = await self.db.execute(
            "DELETE FROM forfeits WHERE chat_id=? AND id=?", (chat_id, forfeit_id)
        )
        await self.db.commit()
        return cur.rowcount == 1

    async def draw_forfeit(self, chat_id: int, week_key: str) -> str | None:
        """Pick a random unused forfeit and mark it used for this week."""
        cur = await self.db.execute(
            "SELECT id, text FROM forfeits WHERE chat_id=? AND used_week IS NULL ORDER BY RANDOM() LIMIT 1",
            (chat_id,),
        )
        row = await cur.fetchone()
        if row is None:
            # All used up — recycle.
            await self.db.execute("UPDATE forfeits SET used_week=NULL WHERE chat_id=?", (chat_id,))
            cur = await self.db.execute(
                "SELECT id, text FROM forfeits WHERE chat_id=? ORDER BY RANDOM() LIMIT 1", (chat_id,)
            )
            row = await cur.fetchone()
            if row is None:
                return None
        await self.db.execute("UPDATE forfeits SET used_week=? WHERE id=?", (week_key, row["id"]))
        await self.db.commit()
        return row["text"]

    # -- idempotent posting ------------------------------------------------

    async def mark_posted(self, chat_id: int, kind: str, key: str) -> bool:
        """Returns True the first time (chat, kind, key) is marked, False on repeats."""
        cur = await self.db.execute(
            "INSERT OR IGNORE INTO posted (chat_id, kind, key) VALUES (?, ?, ?)", (chat_id, kind, str(key))
        )
        await self.db.commit()
        return cur.rowcount == 1
