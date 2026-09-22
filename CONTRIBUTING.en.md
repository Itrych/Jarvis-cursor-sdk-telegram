# Contributing

[Русский](CONTRIBUTING.md)

The repository owner accepts changes. The notes below are the working agreement for the code.

## Setup

Python 3.10 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e .
copy .env.example .env
copy config.example.yaml config.yaml
```

Fill in `.env` and `config.yaml` on your machine. Neither file is committed.

## Checks

Tests use the standard library:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Run them before a commit when file-path handling or the stream text builder changed.

## Style

- Code comments are in English.
- Commit messages are in Russian. State why the change exists.
- One document uses one language. Do not append an English section to a Russian page, or the reverse. Command names, file names, and product names stay as they are.

## Do not commit

- `.env`, tokens, keys, or session databases under `data/`
- `config.yaml` with a machine-specific path
- `_docs/`, `_other/`, `AGENTS.md`, `.cursor/`
- The virtual environment and build caches

If a secret has already landed in history, revoke it and issue a new one. Removing the file from the latest commit is not enough.

## Changes

1. Branch from `main`.
2. Commit in Russian.
3. Add a user-visible note to the [changelog](CHANGELOG.en.md).
4. Open a pull request for the repository owner.

GitHub Releases are written in Russian and point at the matching changelog section.
