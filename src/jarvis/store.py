from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_PROJECT_COLS = (
    "id, name, path, agent_id, model, model_params, created_at, updated_at"
)


class ProjectNameError(ValueError):
    pass


def validate_project_name(name: str) -> str:
    cleaned = name.strip()
    if not _NAME_RE.fullmatch(cleaned):
        raise ProjectNameError(
            "Имя проекта: латиница, цифры, точка, дефис, подчёркивание; до 64 символов."
        )
    if cleaned.upper() in _WINDOWS_RESERVED:
        raise ProjectNameError("Это зарезервированное имя Windows.")
    return cleaned


@dataclass(frozen=True)
class Project:
    id: int
    name: str
    path: str
    agent_id: str | None
    model: str | None
    model_params: tuple[tuple[str, str], ...]
    created_at: str
    updated_at: str


class Store:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    async def init(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    path TEXT NOT NULL UNIQUE,
                    agent_id TEXT,
                    model TEXT,
                    model_params TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id INTEGER PRIMARY KEY,
                    active_project_id INTEGER REFERENCES projects(id)
                );
                """
            )
            await _ensure_column(db, "projects", "model_params", "TEXT")
            await db.commit()

    async def list_projects(self) -> list[Project]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"SELECT {_PROJECT_COLS} FROM projects ORDER BY name COLLATE NOCASE"
            )
            rows = await cur.fetchall()
        return [self._row(r) for r in rows]

    async def get_project(self, project_id: int) -> Project | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"SELECT {_PROJECT_COLS} FROM projects WHERE id = ?",
                (project_id,),
            )
            row = await cur.fetchone()
        return self._row(row) if row else None

    async def get_by_name(self, name: str) -> Project | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"SELECT {_PROJECT_COLS} FROM projects WHERE name = ?",
                (name,),
            )
            row = await cur.fetchone()
        return self._row(row) if row else None

    async def get_by_path(self, path: str) -> Project | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"SELECT {_PROJECT_COLS} FROM projects WHERE path = ?",
                (path,),
            )
            row = await cur.fetchone()
        return self._row(row) if row else None

    async def create_project(
        self,
        name: str,
        path: str,
        model: str | None = None,
        model_params: Sequence[tuple[str, str]] = (),
    ) -> Project:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                "INSERT INTO projects "
                "(name, path, agent_id, model, model_params, created_at, updated_at) "
                "VALUES (?, ?, NULL, ?, ?, ?, ?)",
                (name, path, model, _dump_params(model_params), now, now),
            )
            await db.commit()
            cur = await db.execute(
                f"SELECT {_PROJECT_COLS} FROM projects WHERE name = ?",
                (name,),
            )
            row = await cur.fetchone()
        assert row is not None
        return self._row(row)

    async def set_active(self, chat_id: int, project_id: int | None) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO chats (chat_id, active_project_id) VALUES (?, ?) "
                "ON CONFLICT(chat_id) DO UPDATE SET active_project_id = excluded.active_project_id",
                (chat_id, project_id),
            )
            await db.commit()

    async def get_active(self, chat_id: int) -> Project | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT p.id, p.name, p.path, p.agent_id, p.model, p.model_params, "
                "p.created_at, p.updated_at "
                "FROM chats c JOIN projects p ON p.id = c.active_project_id "
                "WHERE c.chat_id = ?",
                (chat_id,),
            )
            row = await cur.fetchone()
        return self._row(row) if row else None

    async def update_agent(
        self,
        project_id: int,
        agent_id: str | None,
        model: str | None,
        model_params: Sequence[tuple[str, str]] | None = None,
    ) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            if model_params is None:
                await db.execute(
                    "UPDATE projects SET agent_id = ?, model = ?, updated_at = ? WHERE id = ?",
                    (agent_id, model, _now(), project_id),
                )
            else:
                await db.execute(
                    "UPDATE projects SET agent_id = ?, model = ?, model_params = ?, "
                    "updated_at = ? WHERE id = ?",
                    (agent_id, model, _dump_params(model_params), _now(), project_id),
                )
            await db.commit()

    @staticmethod
    def _row(row: aiosqlite.Row) -> Project:
        return Project(
            id=int(row["id"]),
            name=str(row["name"]),
            path=str(row["path"]),
            agent_id=row["agent_id"],
            model=row["model"],
            model_params=_parse_params(row["model_params"] if "model_params" in row.keys() else None),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )


async def _ensure_column(
    db: aiosqlite.Connection, table: str, column: str, decl: str
) -> None:
    cur = await db.execute(f"PRAGMA table_info({table})")
    names = {row[1] for row in await cur.fetchall()}
    if column not in names:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _parse_params(raw: str | None) -> tuple[tuple[str, str], ...]:
    if not raw:
        return ()
    loaded = json.loads(raw)
    if not isinstance(loaded, list):
        return ()
    pairs: list[tuple[str, str]] = []
    for item in loaded:
        if not isinstance(item, dict):
            continue
        key = item.get("id")
        value = item.get("value")
        if isinstance(key, str) and isinstance(value, str):
            pairs.append((key, value))
    return tuple(pairs)


def _dump_params(params: Sequence[tuple[str, str]]) -> str:
    return json.dumps(
        [{"id": key, "value": value} for key, value in params],
        ensure_ascii=False,
    )


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
