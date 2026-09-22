# Jarvis

[Русский](README.md)

A Telegram daemon for local Cursor SDK agents. You send a task from chat. The agent reads and writes files on the machine where Jarvis is running. The editor is only needed when you want to look at the result.

Version `0.1.0`.

## Capabilities

- Telegram long polling. The daemon stays up as long as the process and the network stay up. No public address and no inbound port are required.
- Access is limited to an allowlist of numeric Telegram user ids.
- Several on-disk projects. One project is active in the chat. Switching does not cancel a run in another project.
- A local Cursor SDK agent. The model and the project directory are set explicitly. The conversation continues through `send` and `resume`.
- Model and reasoning-effort selection from the account catalog.
- A live chat reply, edited at most about once a second. A new sentence that starts with a capital letter begins on its own line.
- A project file tree, plus sending a file. A directory or the whole project is sent as a zip when it fits the Telegram size limit.

## How it fits together

```mermaid
flowchart LR
  phone[Telegram]
  daemon[Jarvis]
  sdk[Cursor SDK, local agent]
  disk[Project directories]
  phone -->|long polling| daemon
  daemon --> sdk
  sdk --> disk
```

The model runs in Cursor's cloud. The daemon machine keeps project files, the SQLite session store, and local agent state.

| Path | Role |
| --- | --- |
| This repository | Jarvis itself |
| `projects_root` in `config.yaml` | Agent workspaces. Not the Jarvis source tree |

## Requirements

- Python 3.10 or newer
- Windows x64, which is the system this daemon was exercised on, or another system that has an official `cursor-sdk` wheel (Linux x64/arm64, macOS)
- A dedicated Telegram bot. Do not reuse the Cursor MCP bridge token: two long polls on one token conflict
- A Cursor API key for the account that should be billed
- A machine that stays on. The screen may be locked. The daemon process may not exit

A GPU is not required. CPU and memory load shows up when the agent builds a project, installs packages, or runs tests.

## Install

```powershell
git clone <url-of-this-repository>
cd Jarvis-cursor-sdk-telegram
python -m venv .venv
.\.venv\Scripts\pip install -e .
copy .env.example .env
copy config.example.yaml config.yaml
```

Fill in `.env` and the paths in `config.yaml`. Then:

```powershell
.\.venv\Scripts\python.exe -m jarvis
```

On Windows, `start.bat` in the repository root does the same launch after the virtual environment exists.

Send `/start` to the bot. If the allowlist is empty, the bot replies with your numeric user id. Put that id into `TELEGRAM_ALLOWED_USER_IDS` and restart the daemon. Then `/new` or `/open`, then `/task`.

The chat UI is Russian. Slash commands below are the stable interface. Reply-keyboard buttons trigger the same actions.

## Configuration

Secrets belong only in `.env`. That file is not committed.

| Variable | Meaning |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather |
| `TELEGRAM_ALLOWED_USER_IDS` | Numeric ids, comma-separated. Empty turns `/start` into a setup hint |
| `CURSOR_API_KEY` | A user key or a service-account key |

`config.yaml` holds paths and the default model. See `config.example.yaml`. `config.yaml` is not committed, because it contains this machine's paths.

Keep `projects_root` and `bridge_workspace` stable across restarts. Local agents are tied to the SDK bridge workspace. If the path changes, `resume` may fail to find the previous conversation.

## Commands

| Command | Action |
| --- | --- |
| `/start` | Keyboard and the current project |
| `/help` | Help |
| `/status` | Config, with secrets omitted |
| `/new [name]` | Create a directory under `projects_root` |
| `/open` | Attach an existing directory |
| `/projects` | List projects and switch the active one |
| `/task [text]` | Send a task to the active agent |
| `/files [path]` | File tree |
| `/get path` | Send a file. A directory or `.` is zipped |
| `/model` | Pick a model, then a reasoning effort |
| `/effort` | Change only the effort of the current model |
| `/stop` | Cancel pending input or the current run |

A plain message, when a project is selected, continues the same agent conversation.

Project names use Latin letters, digits, dots, and hyphens. Hidden trees such as `.git`, `venv`, and `node_modules` are left out of listings and archives. Telegram will not accept a document much above 50 MB.

## Limits of 0.1.0

- The chat UI is Russian. There is no Mini App.
- Agents are local only. Cursor cloud runtime is not wired into this daemon.
- One `python -m jarvis` process per bot token.
- Parallel projects exist in the code and are not yet confirmed as a steady mode.
- A Windows service is not part of this version. Start the daemon by hand or with `start.bat`.

## Documents

- [Contributing](CONTRIBUTING.en.md)
- [Security](SECURITY.en.md)
- [Changelog](CHANGELOG.en.md)
- [MIT License](LICENSE)

Later versions are recorded in the changelog and in GitHub Releases. Release text is written in Russian.
