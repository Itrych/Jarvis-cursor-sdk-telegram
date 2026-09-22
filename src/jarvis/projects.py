from __future__ import annotations

from pathlib import Path

from jarvis.store import Project, ProjectNameError, Store, validate_project_name


def scan_project_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        (p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")),
        key=lambda p: p.name.lower(),
    )


async def create_new_project(store: Store, root: Path, name: str, model: str) -> Project:
    name = validate_project_name(name)
    path = (root / name).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ProjectNameError("Путь проекта должен быть внутри projects_root.") from exc
    existing = await store.get_by_name(name)
    if existing:
        raise ProjectNameError(f"Проект {name} уже есть в Jarvis.")
    by_path = await store.get_by_path(str(path))
    if by_path:
        raise ProjectNameError(f"Папка уже привязана как {by_path.name}.")
    root.mkdir(parents=True, exist_ok=True)
    path.mkdir(parents=True, exist_ok=False)
    return await store.create_project(name, str(path), model=model)


async def attach_existing_project(store: Store, root: Path, name: str, model: str) -> Project:
    name = validate_project_name(name)
    path = (root / name).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ProjectNameError("Папка должна быть внутри projects_root.") from exc
    if not path.is_dir():
        raise ProjectNameError(f"Папки {name} нет в projects_root.")
    existing = await store.get_by_path(str(path)) or await store.get_by_name(name)
    if existing:
        return existing
    return await store.create_project(name, str(path), model=model)
