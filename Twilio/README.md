# SMS to Gemini (Twilio Version)

A Flask webhook that bridges SMS/MMS (via [Twilio](https://www.twilio.com/)) to [Google Gemini](https://ai.google.dev/). Text a Twilio number, get an AI reply back as a text — with live sports scores, Google Search grounding, and image (MMS) understanding built in.

This is the actively maintained implementation in this repo. See [`../Google-Voice/`](../Google-Voice/) for an older, Gmail-OAuth-polling implementation that predates Twilio support.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quickstart](#quickstart)
- [Environment Variables](#environment-variables)
- [Local Development](#local-development)
- [Configuring the Twilio Webhook](#configuring-the-twilio-webhook)
- [Deployment](#deployment)
- [How It Works](#how-it-works)
- [API Reference](#api-reference)
- [Session Model & Limitations](#session-model--limitations)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Security Notes](#security-notes)
- [License](#license)

---

## Features

- **AI-powered conversations** via Google Gemini, with a persistent per-sender chat history.
- **Live sports scores** for MLB, NHL, NBA, and NFL, fetched from ESPN through a local [MCP](https://modelcontextprotocol.io/) server (`sports_mcp_server.py`), with fuzzy team-name and league-keyword detection so "how'd the Yanks do" or "nhl scores" both work.
- **Google Search grounding** — Gemini can search the web for up-to-date answers on any query, not just sports.
- **Image understanding** — MMS image attachments are downloaded from Twilio and passed to Gemini for analysis.
- **Automatic retry with backoff** on transient Gemini errors (503s, rate limits).
- **`/new` command** — text `/new` to reset your conversation history.
- **Render-ready** — includes `Procfile`, `render.yaml`, and a stable `app.py` entrypoint for Gunicorn.

## Architecture

```
                     POST /sms (TwiML webhook)
   Twilio  ───────────────────────────────────▶  Flask app (app.py / sms_gemini.py)
     ▲                                                     │
     │  TwiML <Message> reply                              │  1. Detect sports intent (regex/fuzzy match)
     │                                                      │  2. If sports: query sports_mcp_server.py
     └──────────────────────────────────────────────────┐  │     (subprocess over MCP stdio) → ESPN API
                                                          │  │  3. Download any MMS images (Twilio media API)
                                                          │  │  4. Send prompt + images + scores to Gemini
                                                          │  ▼     (with Google Search tool enabled)
                                                     Google Gemini API
```

Two entrypoints exist for the same app:
- **`sms_gemini.py`** — the actual Flask application and all logic.
- **`app.py`** — a thin wrapper that dynamically loads `sms_gemini.py` and exposes `app`. This exists so Gunicorn always has a stable `app:app` target even if `sms_gemini.py` is renamed or restructured. Use `app.py` in production (Gunicorn/Render); either file works for local `python` runs.

## Prerequisites

1. **Google AI Studio API key** — get one at [aistudio.google.com](https://aistudio.google.com/).
2. **Twilio account** with a phone number that has SMS/MMS capability.
3. **Python 3.10+**.

## Quickstart

```bash
git clone https://github.com/Felzy613/SMS-to-Gemini.git
cd SMS-to-Gemini/Twilio

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env             # then edit .env with your real values

python app.py                    # serves on http://localhost:5000
```

## Environment Variables

See [`.env.example`](.env.example) for a ready-to-copy template.

| Variable | Required | Default | Description |
|---|---|---|---|
| `API_KEY` | Yes | — | Google AI Studio (Gemini) API key. App refuses to start without it. |
| `TWILIO_ACCOUNT_SID` | Yes* | — | Twilio Account SID. *Required for downloading MMS images; the app still runs without it, but image messages are skipped with a warning logged. |
| `TWILIO_AUTH_TOKEN` | Yes* | — | Twilio Auth Token, paired with the SID above for authenticating media downloads. |
| `GEMINI_MODEL_ID` | No | `gemini-3.flash-preview` | Gemini model used for chat. |
| `LOG_LEVEL` | No | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `MAX_RETRIES` | No | `5` | Retry attempts for a failed Gemini call before giving up. |
| `INITIAL_RETRY_DELAY` | No | `1` | Seconds before the first retry; doubles each attempt (exponential backoff). |
| `SPORTS_MCP_PYTHON` | No | current interpreter | Python executable used to launch the sports MCP subprocess. |
| `SPORTS_MCP_SERVER_PATH` | No | `sports_mcp_server.py` next to `app.py` | Path to the sports MCP server script. |
| `HOST` | No | `0.0.0.0` | Bind host — only used by `python app.py`; ignored by Gunicorn/Render. |
| `PORT` | No | `5000` | Bind port — only used by `python app.py`; Render sets `$PORT` itself. |

> **Note:** the default for `GEMINI_MODEL_ID` (`gemini-3.flash-preview`) has a period where a hyphen is likely intended (compare `Google-Voice/sms_gemini.py`'s `gemini-3-flash-preview`). If Gemini calls fail with a "model not found" error, set `GEMINI_MODEL_ID` explicitly to a model ID you've confirmed exists.

## Local Development

Twilio needs a public URL to send webhooks to. Use [ngrok](https://ngrok.com/) to expose your local server:

```bash
python app.py
```

In a second terminal:

```bash
ngrok http 5000
```

Copy the `https://...` URL ngrok prints and use it (with `/sms` appended) as your Twilio webhook — see below.

## Configuring the Twilio Webhook

1. Open the [Twilio Console](https://www.twilio.com/console).
2. Go to **Phone Numbers → Manage → Active Numbers** and click your number.
3. Scroll to **Messaging**.
4. Under **A MESSAGE COMES IN**, choose **Webhook**, set the method to `HTTP POST`, and paste your URL, e.g.:
   - `https://your-app.onrender.com/sms` (production), or
   - `https://<your-ngrok-subdomain>.ngrok-free.app/sms` (local dev).
5. Click **Save**.

## Deployment

This project is pre-configured for [Render](https://render.com/); see [`DEPLOYMENT.md`](DEPLOYMENT.md) for the full guide and a generic/self-hosted (Docker/Gunicorn) alternative.

## How It Works

1. **Inbound SMS/MMS** — Twilio POSTs form-encoded data to `/sms` (sender number, message body, and any `MediaUrl{N}`/`MediaContentType{N}` fields for MMS attachments).
2. **Image extraction** — for each attached image, `fetch_twilio_image()` downloads it from Twilio's media URL (HTTP Basic Auth using your Account SID/Auth Token) and loads it into memory as a Pillow `Image`.
3. **Sports intent detection** — the message text is broken into 1-3 word n-grams and fuzzy-matched (via `difflib`) against league keywords (`mlb`, `nba`, ...), ~120 team names, and generic phrases like "scores" or "who's playing". A match determines which league(s), if any, to fetch, and whether the request is team-specific (so results are filtered to that team) or league-wide.
4. **Sports data (if matched)** — the Flask app spawns `sports_mcp_server.py` as an MCP subprocess over stdio and calls its `get_live_scores` tool, which hits ESPN's public scoreboard API per league and returns formatted score lines. If the MCP call fails for any reason, the app degrades gracefully and tells the user live scores are unavailable — it does not crash the request.
5. **Gemini call** — the (possibly sports-augmented) prompt, plus any images, is sent to the sender's ongoing Gemini chat session. The Google Search tool is enabled on every call, so Gemini can pull in current information for non-sports questions too. On transient errors (503 / rate limit), the app retries up to `MAX_RETRIES` times with exponential backoff; other errors fail immediately with a generic apology message.
6. **Outbound SMS** — the response text is normalized (markdown `*` stripped, whitespace collapsed) and returned to Twilio as TwiML (`<Response><Message>...</Message></Response>`), which Twilio then sends as an SMS reply.

## API Reference

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness check. Returns `{"status": "ok"}` with HTTP 200. Useful for Render/uptime monitors. |
| `POST` | `/sms` | Twilio's SMS/MMS webhook target. Expects Twilio's standard form fields (`From`, `Body`, `NumMedia`, `MediaUrl{N}`, `MediaContentType{N}`). Returns `Content-Type: application/xml` TwiML. Not meant to be called directly outside of Twilio (or a signed test request). |

## Session Model & Limitations

- **In-memory, per-process sessions.** Chat history is kept in a Python dict keyed by sender phone number (`chat_sessions`), living only in the process's RAM.
- **No persistence across restarts/deploys.** A redeploy, crash, or scale event wipes every user's conversation history. There's no database or external session store.
- **Not safe for multiple worker processes.** `render.yaml`/`Procfile` run Gunicorn with `--workers 1` specifically because sessions live in process memory — running more than one worker would silently split each user's messages across separate, inconsistent chat histories. If you need multiple workers (for throughput), you'll need to move session state to something shared (Redis, a database, etc.) first.
- **Users reset their own session** by texting `/new`.

## Project Structure

```
Twilio/
├── app.py                  # Stable Gunicorn entrypoint (imports sms_gemini.py, exposes `app`)
├── sms_gemini.py            # Flask app: routes, Gemini calls, sports-intent detection, Twilio media handling
├── sports_mcp_server.py     # Standalone MCP server exposing get_live_scores (ESPN scoreboard data)
├── requirements.txt
├── Procfile                 # `web: gunicorn app:app ...` (used by some PaaS providers)
├── render.yaml               # Render Blueprint (build/start commands, env vars)
├── DEPLOYMENT.md
├── .env.example
└── .vscode/settings.json    # Points the Python extension at .venv
```

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| App won't start: `RuntimeError: Missing required environment variable: API_KEY` | Set `API_KEY` in your environment or `.env` file. |
| Replies never arrive, but `/health` works | Check the Twilio webhook URL is correct, points to `/sms`, uses `HTTP POST`, and is publicly reachable (ngrok tunnel still running, or your deploy is up). Check Twilio's [debugger console](https://www.twilio.com/console/debugger) for webhook errors. |
| MMS images are ignored | `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN` aren't set — image downloads are skipped (with a logged warning) without them. |
| "Unable to retrieve live scores" | The sports MCP subprocess failed to start or ESPN's API errored/timed out; check logs for the underlying exception. This never crashes the request — Gemini still answers using whatever text was sent. |
| Every user seems to share one conversation, or history randomly resets | You're likely running more than one Gunicorn worker/process. Keep `--workers 1` (see [Session Model & Limitations](#session-model--limitations)), or move sessions to shared storage. |
| Local testing: Twilio can't reach `localhost:5000` | You need a public tunnel — see [Local Development](#local-development) (ngrok). |

## Security Notes

- Never commit a real `.env` file — `.gitignore` already excludes it. Use `.env.example` as your template.
- `TWILIO_AUTH_TOKEN` and `API_KEY` are secrets; treat them like passwords (Render's dashboard env vars, not source control).
- The `/sms` endpoint does not currently validate Twilio's `X-Twilio-Signature` header, so it will process POSTs from any source, not just Twilio. If you expose this publicly and want to harden it, add [request validation](https://www.twilio.com/docs/usage/webhooks/webhooks-security) before processing.

## License

MIT — see the repository's [`LICENSE`](../LICENSE) file.
