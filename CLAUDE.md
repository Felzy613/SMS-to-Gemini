# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Structure

This repo contains **two independent, unrelated implementations** of the same idea (bridge SMS to Google Gemini) — they share no code, no dependencies, and no virtual environment:

- **`Twilio/`** — actively maintained. A Flask webhook that receives SMS/MMS from Twilio and replies via TwiML.
- **`Google-Voice/`** — older, still functional. A long-running polling loop that reads a Gmail inbox (fed by Google Voice's "forward texts to email") via the Gmail API and replies by sending email back through the same thread.

Always work inside the correct subfolder — there is no root-level `requirements.txt` or shared entrypoint. Each subfolder has its own `README.md` with full setup/deployment/troubleshooting detail; this file only covers what's needed to be productive across both.

## Commands

Each subproject needs its own venv and its own install:

```bash
# Twilio/
cd Twilio && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env   # fill in API_KEY, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
python app.py           # serves on :5000; needs an ngrok tunnel for Twilio to reach it locally

# Google-Voice/
cd Google-Voice && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env   # fill in API_KEY, EMAIL_ADDRESS
# also requires credentials.json (Gmail OAuth client) in this directory — see Google-Voice/README.md
python sms_gemini.py    # long-running poll loop; Ctrl+C to stop
```

There are **no automated tests and no lint/formatter config** in this repo. Verify changes by running the app and exercising it manually (see each subfolder's README for local-dev instructions — ngrok for `Twilio/`, a real Google Voice number forwarding to Gmail for `Google-Voice/`), plus `python -m py_compile <file>` as a cheap syntax sanity check.

## Architecture

### `Twilio/` — webhook, request-driven

- **`app.py`** is the stable Gunicorn entrypoint (`gunicorn app:app`). It dynamically loads `sms_gemini.py` by file path and re-exports its Flask `app` object — this indirection exists so the process-manager target (`app:app`) never has to change even if `sms_gemini.py` is edited or renamed. When editing routes/logic, edit **`sms_gemini.py`**, not `app.py`.
- **`sms_gemini.py`** is the whole application: Flask routes (`/health`, `POST /sms`), sports-intent detection (n-gram + `difflib` fuzzy matching against league keywords and ~120 team names), Twilio MMS image download, and the Gemini call with retry/backoff.
- **`sports_mcp_server.py`** is a separate MCP server (FastMCP) exposing one tool, `get_live_scores`, that hits ESPN's public scoreboard API. `sms_gemini.py` launches it as a **subprocess over MCP stdio** (`stdio_client`/`ClientSession`) per sports-related request rather than importing it — treat it as a separate process boundary, not a library. If MCP is unavailable or the subprocess fails, `sms_gemini.py` degrades gracefully (tells the user scores are unavailable) rather than failing the whole request.
- **Session state is an in-memory Python dict** (`chat_sessions`, keyed by sender phone number) with no persistence or external store. This is why `Procfile`/`render.yaml` pin `--workers 1` — running multiple worker processes would split each phone number's conversation across inconsistent in-memory histories. If you ever need more throughput, session storage has to move to something shared (Redis, DB, etc.) *before* adding workers.
- Nearly all behavior is env-var-configured (model ID, retry counts, MCP subprocess path/interpreter, etc.) — see `Twilio/README.md`'s Environment Variables table before hardcoding something that's likely meant to be configurable.

### `Google-Voice/` — polling loop, long-running process

- **`sms_gemini.py`** is the entire app: Gmail OAuth (`credentials.json` + cached `token.pickle`), a `while True` poll loop (`main()`) checking for unread mail from `@txt.voice.google.com` every 4 seconds, image-attachment extraction, a Gemini call (NHL-scores-only sports augmentation, simpler than Twilio's), and replying via `Gmail.users().messages().send`.
- This has **no HTTP server and no webhook** — it must be kept running continuously on a machine you control (systemd/launchd/Task Scheduler/tmux), not deployed like a typical PaaS web service. See `Google-Voice/README.md#keeping-it-running`.
- Same in-memory `chat_sessions` pattern as the Twilio app, with the same single-process constraint (never run two instances against the same Gmail account — you'll get racing/duplicate replies).
- `credentials.json`, `token.pickle`, and the `attachments/` folder (saved MMS images) are all gitignored and must never be committed — they hold live OAuth secrets and other people's message content.

### Shared conventions across both

- Every secret/config value is read via `os.getenv(...)`, never hardcoded — follow that pattern for anything new.
- Both apps normalize Gemini's response text before sending it out (strip markdown `*`, collapse whitespace) since it's headed to a plain-text SMS.
- Both support a `/new` text command that resets the sender's chat session.
- `LICENSE` at the repo root covers both subprojects (MIT); `Google-Voice/LICENSE` is a duplicate of the same text, kept for that folder's standalone history.

## Codex config detected

A Codex CLI config exists at `~/.codex/config.toml` (user-level, not project-level). Reply `/import` to scan it (MCP servers, instructions, etc.) and see what's importable, then `/import --yes=<digest>` to apply.
