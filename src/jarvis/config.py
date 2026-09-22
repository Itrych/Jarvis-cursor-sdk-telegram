from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


class Settings(BaseModel):
    repo_root: Path
    projects_root: Path
    bridge_workspace: Path
    default_model: str = "composer-2.5"
    telegram_bot_token: str = ""
    cursor_api_key: str = ""
    allowed_user_ids: frozenset[int] = Field(default_factory=frozenset)
    db_path: Path

    @field_validator("projects_root", "bridge_workspace", "db_path", mode="before")
    @classmethod
    def expand_path(cls, value: Path | str) -> Path:
        return Path(str(value)).expanduser()

    @property
    def telegram_ready(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def cursor_ready(self) -> bool:
        return bool(self.cursor_api_key)

    @property
    def bootstrap_acl(self) -> bool:
        return not self.allowed_user_ids


def load_settings(root: Path | None = None) -> Settings:
    root = root or repo_root()
    load_dotenv(root / ".env")

    config_path = root / "config.yaml"
    if not config_path.exists():
        config_path = root / "config.example.yaml"

    raw: dict = {}
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"Config {config_path} must be a mapping")
        raw = loaded

    cursor = raw.get("cursor") or {}
    telegram = raw.get("telegram") or {}
    projects_root = Path(raw.get("projects_root") or (Path.home() / "jarvis-projects"))
    bridge_workspace = Path(cursor.get("bridge_workspace") or projects_root)

    allowed: set[int] = set()
    for item in telegram.get("allowed_user_ids") or []:
        allowed.add(int(item))
    env_ids = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").strip()
    if env_ids:
        for part in env_ids.split(","):
            part = part.strip()
            if part:
                allowed.add(int(part))

    return Settings(
        repo_root=root,
        projects_root=projects_root,
        bridge_workspace=bridge_workspace,
        default_model=str(cursor.get("default_model") or "composer-2.5"),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        cursor_api_key=os.getenv("CURSOR_API_KEY", "").strip(),
        allowed_user_ids=frozenset(allowed),
        db_path=root / "data" / "jarvis.sqlite3",
    )
