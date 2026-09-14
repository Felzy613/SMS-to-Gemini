# SMS to Google Gemini (Google Voice / Gmail Version)

A Python chatbot that bridges your **Google Voice** number to **Google Gemini** through Gmail. Google Voice forwards incoming texts to a Gmail inbox as email; this script polls that inbox via the Gmail API, sends each message (and any MMS image attachments) to Gemini, and emails the reply back — which Google Voice then forwards out as a text.

> This is an older, polling-based implementation. The actively maintained version of this project is [`../Twilio/`](../Twilio/), a Flask webhook that talks to Twilio directly instead of relaying through Gmail/Google Voice. Use this folder if you specifically want to keep using a free Google Voice number rather than a paid Twilio number.

---

## Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
  - [Install Dependencies](#install-dependencies)
  - [Environment Variables](#environment-variables)
- [Configuration](#configuration)
  - [Google Gemini API Key](#google-gemini-api-key)
  - [Gmail API & OAuth Credentials](#gmail-api--oauth-credentials)
  - [Google Voice Number](#google-voice-number)
- [Running the Script](#running-the-script)
- [Features](#features)
- [Limitations](#limitations)
- [Keeping It Running](#keeping-it-running)
- [Troubleshooting & FAQ](#troubleshooting--faq)
- [Security Notes](#security-notes)
- [License](#license)
- [Disclaimer](#disclaimer)

---

## Overview

Unlike the Twilio version (which receives an HTTP webhook the instant a text arrives), this script has no inbound endpoint at all — it's a long-running loop that **polls** a Gmail inbox every few seconds for new messages forwarded from Google Voice, processes them, and replies by sending an email back through the same thread. It needs to keep running continuously (see [Keeping It Running](#keeping-it-running)); it's not something you deploy as a typical web service.

## How It Works

1. **Authenticate** with the Gmail API using OAuth2 (`gmail_authenticate()` in [`sms_gemini.py`](sms_gemini.py)) — opens a browser for consent on first run, then caches a token in `token.pickle` for subsequent runs.
2. **Poll** (`main()`) — every 4 seconds, search for unread mail from `@txt.voice.google.com` (Google Voice's forwarding address).
3. **Parse** (`read_gmail()`) — for each match, extract the plain-text body and any image attachments (downloading them into a local `attachments/` folder), then mark the email read.
4. **Generate a reply** (`generate_and_send_response()`) — send the text (plus any images) to a per-sender Gemini chat session, with Google Search enabled as a tool. If the message mentions NHL scores, live scores from ESPN are fetched and appended to the prompt first. Failed calls retry with exponential backoff.
5. **Reply** (`send_email()`) — the Gemini response is emailed back to the original sender address, threaded via `In-Reply-To`/`References` headers. Google Voice picks this up and texts it out.

Texting `/new` to the bot resets that sender's conversation history.

## Prerequisites

- **Python 3.10+**.
- A **Google Cloud project** with the **Gmail API** enabled, and access to the **Gemini API**.
- A **Gmail account** (a dedicated one is strongly recommended — see [Security Notes](#security-notes)) with **OAuth 2.0 Desktop app credentials**.
- A **Google Voice number**, with SMS forwarding to that Gmail account's inbox enabled.
- A **Gemini API key** from [Google AI Studio](https://aistudio.google.com/).

## Setup

### Install Dependencies

```bash
cd SMS-to-Gemini-Twilio/Google-Voice

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

`requirements.txt` includes:

| Package | Purpose |
|---|---|
| `google-genai` | Gemini API client. |
| `google-auth-oauthlib` | OAuth2 flow for Gmail API access. |
| `google-api-python-client` | Gmail API client (`googleapiclient.discovery.build`). |
| `requests` | HTTP calls (ESPN scoreboard API). |
| `pillow` | Opens saved MMS image attachments before sending them to Gemini. |
| `python-dotenv` | Loads `.env` automatically so you don't have to export env vars manually. |

### Environment Variables

Copy [`.env.example`](.env.example) to `.env` and fill in real values:

```env
API_KEY=your_google_genai_api_key
EMAIL_ADDRESS=your_gmail_address@gmail.com
```

`GEMINI_MODEL_ID` and `LOG_LEVEL` are also supported, optionally — see the comments in `.env.example`.

`credentials.json` and `token.pickle` are **not** environment variables — they're files the script reads directly from its working directory (see below). Both are gitignored; never commit them.

## Configuration

### Google Gemini API Key

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a project.
3. Enable the Generative AI / Gemini API for it.
4. Go to **APIs & Services → Credentials → Create Credentials → API Key**.
5. Put the key in `.env` as `API_KEY`.

### Gmail API & OAuth Credentials

1. In the same (or another) Google Cloud project, enable the **Gmail API** (**APIs & Services → Library**, search "Gmail API", **Enable**).
2. Configure the **OAuth consent screen** (**APIs & Services → OAuth consent screen**): choose **External**, fill in the required fields, and add the `gmail.modify` scope (the script requests `https://www.googleapis.com/auth/gmail.modify`, needed to read messages and remove the unread label).
3. Create credentials: **APIs & Services → Credentials → Create Credentials → OAuth client ID**, application type **Desktop app**.
4. Download the resulting JSON file, rename it to `credentials.json`, and place it in this `Google-Voice/` directory (next to `sms_gemini.py`).
5. On first run, the script opens a browser window for you to sign in and consent; it then writes `token.pickle` so future runs don't need to re-authenticate. Delete `token.pickle` to force re-authentication (e.g., if you change scopes or accounts).

### Google Voice Number

1. Sign in to [Google Voice](https://voice.google.com/) using the **same Gmail account** you just set up OAuth for.
2. Get a Google Voice number if you don't already have one.
3. Open **Settings → Messages** and enable **Forward messages to email**, confirming it points at that same Gmail address.

## Running the Script

```bash
python sms_gemini.py
```

The script authenticates, then loops indefinitely: polling Gmail, generating Gemini replies, and sending them back. Press `Ctrl+C` to stop.

## Features

- Per-sender persistent Gemini chat sessions (reset any one with `/new`).
- Image (MMS) attachment support — downloaded, opened with Pillow, and sent to Gemini alongside the text.
- Google Search tool enabled on every Gemini call for up-to-date answers.
- Live **NHL** scores from ESPN, appended automatically when a message mentions them.
- Automatic retry with exponential backoff on transient (503 / rate-limited) Gemini errors.
- Self-restart on a known intermittent Gmail SSL error ("EOF occurred in violation of protocol") or if Gmail authentication fails on startup — relaunches itself as a new process rather than crashing out silently.

## Limitations

Compared to the [Twilio version](../Twilio/):

- **NHL scores only** — no MLB, NBA, or NFL support (the Twilio version supports all four with fuzzy team-name matching).
- **No MCP integration** — sports scores are fetched with a plain HTTP call, not through a Model Context Protocol server.
- **Polling, not push** — replies arrive within one polling interval (up to ~4 seconds) of Gmail actually delivering the forwarded message, rather than instantly on webhook delivery; Google's own mail delivery/forwarding latency is typically the larger factor.
- **In-memory sessions** — like the Twilio version, `chat_sessions` lives only in process memory. Restarting the script clears everyone's conversation history.
- **Single process only** — there's no concept of multiple workers here; run exactly one instance against a given Gmail account, or you'll get duplicate/racing replies.

## Keeping It Running

Because this is a polling loop, not a request-driven web service, it needs to be kept alive continuously on a machine (or server) you control — it isn't a fit for typical serverless/PaaS hosting the way the Twilio version is. Options:

- **`systemd`** (Linux): create a service unit similar to the one in [`../Twilio/DEPLOYMENT.md`](../Twilio/DEPLOYMENT.md#bare-vps-systemd--gunicorn), but with `ExecStart=.../.venv/bin/python sms_gemini.py` and no Gunicorn involved.
- **`launchd`** (macOS) or **Task Scheduler** (Windows) for a background/login-time process.
- A persistent `tmux`/`screen` session on a small always-on VPS, for a lighter-weight setup.

Whatever you choose, make sure `credentials.json` and `token.pickle` are present in the working directory the process runs from, and that `.env` (or real environment variables) are loaded before `sms_gemini.py` starts.

## Troubleshooting & FAQ

**Gmail API authorization fails or loops back to the browser every run**
Verify `credentials.json` is in the `Google-Voice/` directory and matches the OAuth client you configured. Delete `token.pickle` and re-run to force a fresh OAuth flow if you've changed scopes, projects, or accounts.

**`RuntimeError`/no response: API key errors**
Confirm `API_KEY` in `.env` matches a real, active key from Google AI Studio, and that `.env` is actually being loaded (check for a `python-dotenv` import error in the logs — it should be installed by `requirements.txt`).

**No replies are going out, but the script is running**
Check that the Google Voice number's **Forward messages to email** setting still points at the correct Gmail address, and that `EMAIL_ADDRESS` in `.env` matches that same address.

**Can it generate images, not just read them?**
No — image *generation* isn't implemented; only image *understanding* (analyzing MMS attachments you send in) is supported.

**How do I check it's actually receiving texts?**
Watch the logs (`LOG_LEVEL=DEBUG` for more detail) — each processed message logs its subject, content, and the bot's response.

## Security Notes

- `credentials.json` (your OAuth client secret) and `token.pickle` (a cached, live OAuth token with mail read/modify access) are both gitignored. Never commit either — anyone with `token.pickle` can read and modify that Gmail inbox until the token is revoked.
- MMS images are saved locally to `attachments/` (also gitignored) and are never deleted automatically — periodically clear this folder if you're sending sensitive images through the bot.
- Use a **dedicated** Gmail account for this, not your primary one — the OAuth scope (`gmail.modify`) grants read/modify access to the whole inbox, and the account will also be the one at risk if Google flags the automation (see [Disclaimer](#disclaimer)).

## License

MIT — see the repository's [`LICENSE`](../LICENSE) file (also duplicated in this folder as [`LICENSE`](LICENSE)).

## Disclaimer

**Use at your own risk.** Google Voice's terms don't anticipate automated, bot-driven texting, and Google may flag or suspend a Google Voice (or the underlying Google) account it detects behaving this way. Consider this an experimental/hobby setup, not something to depend on for anything important.
