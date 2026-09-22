# Changelog

[Русский](CHANGELOG.md)

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Repository versions match `version` in `pyproject.toml`.

## [0.1.0] - 2026-09-22

First publication of the private repository.

### Added

- A Telegram long-polling daemon: commands and matching buttons, plus an allowlist of user ids.
- On-disk projects: create, attach an existing directory, one active project per chat, SQLite storage.
- A local Cursor SDK agent: create, continue a conversation, switch model, cancel a run, stream into one chat message.
- Model and reasoning-effort selection from the SDK catalog.
- A project file listing, and sending a file or a zip of a directory.
- A line break between stream phrases when a new phrase starts with a capital letter after the end of a sentence.
- Tests for the path sandbox, zip packaging, and stream text assembly.

### Limits

- Parallel projects are not confirmed as a steady mode.
- A Windows service is not part of this version.

[0.1.0]: https://github.com/Itrych/Jarvis-cursor-sdk-telegram/releases/tag/v0.1.0
