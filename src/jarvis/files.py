from __future__ import annotations

import os
import re
import zipfile
from collections.abc import Iterator
from pathlib import Path

SKIP_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".idea",
    ".vs",
}
SKIP_SUFFIXES = {".pyc", ".pyo", ".pyd"}
MAX_LIST_ENTRIES = 400
MAX_SEND_BYTES = 49 * 1024 * 1024


class ProjectPathError(ValueError):
    pass


class DownloadIndex:
    def __init__(self) -> None:
        self._items: dict[int, list[str]] = {}

    def store(self, chat_id: int, rel_paths: list[str]) -> None:
        self._items[chat_id] = rel_paths

    def get(self, chat_id: int, index: int) -> str | None:
        items = self._items.get(chat_id) or []
        if 0 <= index < len(items):
            return items[index]
        return None


def resolve_inside(root: Path, rel: str) -> Path:
    base = root.resolve()
    cleaned = (rel or ".").replace("\\", "/").strip()
    if not cleaned or cleaned in {".", "./"}:
        return base
    if cleaned.startswith("/") or re.match(r"^[A-Za-z]:", cleaned):
        raise ProjectPathError("Нужен относительный путь внутри проекта.")
    target = (base / cleaned).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ProjectPathError("Путь вне проекта.") from exc
    return target


def relative_posix(root: Path, path: Path) -> str:
    rel = path.resolve().relative_to(root.resolve())
    text = rel.as_posix()
    return "." if text == "." else text


def iter_listed_paths(root: Path, start: Path | None = None) -> Iterator[Path]:
    origin = start or root
    if origin.is_file():
        yield origin
        return
    count = 0
    for dirpath, dirnames, filenames in os.walk(origin, topdown=True, followlinks=False):
        dirnames[:] = sorted(
            name for name in dirnames if name not in SKIP_DIR_NAMES and not name.startswith(".")
        )
        current = Path(dirpath)
        if current != origin:
            yield current
            count += 1
            if count >= MAX_LIST_ENTRIES:
                return
        for name in sorted(filenames):
            if Path(name).suffix.lower() in SKIP_SUFFIXES:
                continue
            if name.startswith(".") and name not in {".gitignore", ".env.example"}:
                continue
            yield current / name
            count += 1
            if count >= MAX_LIST_ENTRIES:
                return


def format_tree(root: Path, start: Path | None = None) -> tuple[str, list[str], bool]:
    origin = start or root
    lines: list[str] = []
    top_level: list[str] = []
    truncated = False
    listed = 0
    for path in iter_listed_paths(root, origin):
        listed += 1
        if listed > MAX_LIST_ENTRIES:
            truncated = True
            break
        rel = relative_posix(origin if origin.is_dir() else origin.parent, path)
        display = relative_posix(root, path)
        indent = "  " * (rel.count("/") if rel != "." else 0)
        if path.is_dir():
            lines.append(f"{indent}{path.name}/")
            if rel != "." and rel.count("/") == 0:
                top_level.append(display + "/")
        else:
            lines.append(f"{indent}{path.name}  {human_size(path.stat().st_size)}")
            if rel != "." and rel.count("/") == 0:
                top_level.append(display)
    truncated = truncated or listed >= MAX_LIST_ENTRIES
    if not lines:
        lines.append("(пусто)")
    return "\n".join(lines), top_level, truncated


def zip_target(root: Path, target: Path, dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if target.is_file():
            archive.write(target, target.name)
        else:
            base_name = target.name if target != root else root.name
            for path in iter_listed_paths(root, target):
                if path.is_dir():
                    continue
                rel = path.relative_to(target)
                archive.write(path, Path(base_name, rel).as_posix())
    size = dest.stat().st_size
    if size > MAX_SEND_BYTES:
        dest.unlink(missing_ok=True)
        raise ProjectPathError(
            f"Архив слишком большой для Telegram ({human_size(size)}, лимит 50 МБ)."
        )
    return size


def ensure_sendable_file(path: Path) -> None:
    if not path.exists():
        raise ProjectPathError("Нет такого файла или папки.")
    if path.is_file() and path.stat().st_size > MAX_SEND_BYTES:
        raise ProjectPathError(
            f"Файл слишком большой для Telegram ({human_size(path.stat().st_size)}, лимит 50 МБ)."
        )


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if value < 1024 or unit == "ГБ":
            if unit == "Б":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} Б"
