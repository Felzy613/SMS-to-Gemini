# SMS to Gemini

Text an AI. Two ways to wire it up, in one repo:

| | [`Twilio/`](Twilio/) | [`Google-Voice/`](Google-Voice/) |
|---|---|---|
| **Status** | ✅ Actively maintained | 🕰️ Older, still works |
| **SMS provider** | Twilio (paid number) | Google Voice (free number) |
| **Transport** | Inbound webhook (Flask) | Polls Gmail via the Gmail API |
| **Sports scores** | MLB, NHL, NBA, NFL via a local MCP server, with fuzzy team-name matching | NHL only, via a direct ESPN call |
| **Hosting model** | Any PaaS/web host (Render-ready) | Long-running background process |
| **Images (MMS)** | ✅ | ✅ |
| **Google Search grounding** | ✅ | ✅ |

Both send your message (and any image attachments) to [Google Gemini](https://ai.google.dev/), keep a running conversation per sender, support a `/new` command to reset it, and reply back as a text.

**Start with [`Twilio/`](Twilio/README.md)** unless you specifically want to avoid paying for a Twilio number and are fine running a background process instead of a normal web service — in which case see [`Google-Voice/`](Google-Voice/README.md).

## Repository Layout

```
SMS-to-Gemini-Twilio/
├── Twilio/                  # Flask + Twilio webhook implementation (recommended)
│   ├── README.md             # Full setup, deployment, architecture, troubleshooting
│   ├── DEPLOYMENT.md         # Render + Docker/VPS deployment guide
│   ├── app.py                 # Gunicorn entrypoint
│   ├── sms_gemini.py          # Flask app / core logic
│   ├── sports_mcp_server.py   # MCP server: live ESPN scores (MLB/NHL/NBA/NFL)
│   └── .env.example
├── Google-Voice/             # Gmail-OAuth-polling implementation (older)
│   ├── README.md              # Full setup, Gmail/OAuth config, limitations
│   ├── sms_gemini.py           # Polling loop / core logic
│   └── .env.example
└── LICENSE                    # MIT, covers the whole repo
```

## Quick Start

Pick one implementation and follow its own README — they have different prerequisites (a Twilio account vs. a Google Cloud project + Gmail OAuth setup) and are entirely independent of each other:

- **[Twilio/README.md](Twilio/README.md)** — Flask webhook, deploy anywhere, `pip install -r Twilio/requirements.txt`.
- **[Google-Voice/README.md](Google-Voice/README.md)** — Gmail polling loop, runs continuously on a machine you control, `pip install -r Google-Voice/requirements.txt`.

Each subfolder is self-contained: its own `requirements.txt`, its own `.env.example`, its own virtual environment. There's no shared code or shared dependency between them.

## Security

Both apps read secrets (API keys, Twilio credentials, Gmail OAuth tokens) from environment variables or local files — never from source. See each subfolder's README for its own Security Notes section (in short: keep `.env`, `credentials.json`, and `token.pickle` out of version control — the repo's [`.gitignore`](.gitignore) already excludes all of them).

If you're forking or self-hosting either app, treat every API key and token the same way you'd treat a password.

## License

MIT — see [`LICENSE`](LICENSE).
