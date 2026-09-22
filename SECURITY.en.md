# Security

[Русский](SECURITY.md)

Jarvis is a remote control for the machine it runs on. A local Cursor SDK agent reads the project tree and can run commands as the same user as the daemon.

## Reporting a problem

Do not attach tokens, API keys, `.env` contents, or session dumps.

For this private repository, contact the owner through GitHub. There is no public contact and no bug-bounty program.

## What is already limited

- The bot answers only users listed in `TELEGRAM_ALLOWED_USER_IDS` and `allowed_user_ids`. While that list is empty, working commands stay closed: `/start` only shows the numeric id.
- Secrets are read from `.env`. The repository contains empty examples only.
- Downloads are allowed only inside the active project directory. A path such as `../` is rejected.
- Archives skip service directories such as `.git`, `venv`, and `node_modules`.

## What stays with the operator

- The Jarvis bot token must not be the token of another long poll, including the Cursor MCP bridge.
- The Cursor API key spends the account quota. Keep it only in `.env` on the daemon machine.
- The daemon sees the files of the Windows or Linux account that started it. Do not run it as an administrator unless you need that.
- `projects_root` should not point at a tree of unrelated secrets.
- If the server is lost or `.env` leaks, revoke the bot token in BotFather and the key in the Cursor dashboard, then issue new ones.
