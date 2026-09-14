# Deployment Guide

## Render (recommended)

This project is pre-configured for [Render](https://render.com/) with:
- `app.py` — stable module entrypoint for Gunicorn.
- `Procfile` — `web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`.
- `render.yaml` — a Render Blueprint that defines the service.

### Steps

1. Push this repo to GitHub (or your Git provider of choice).
2. In the Render dashboard, create a new **Web Service** from the repo, with **Root Directory** set to `Twilio`.
   - Render will detect `render.yaml` automatically if it's present at the repo root; since it instead lives at `Twilio/render.yaml`, either point Render's Blueprint at that path or configure the service manually with the settings below.
3. Manual settings (if not using the Blueprint):
   - **Runtime**: `Python 3`
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
4. Set environment variables in the Render dashboard (see [`README.md`'s Environment Variables table](README.md#environment-variables) for the full list):
   - `API_KEY` (required)
   - `TWILIO_ACCOUNT_SID` (required for MMS image download)
   - `TWILIO_AUTH_TOKEN` (required for MMS image download)
   - `GEMINI_MODEL_ID` (optional)
   - `LOG_LEVEL`, `MAX_RETRIES`, `INITIAL_RETRY_DELAY`, `SPORTS_MCP_PYTHON`, `SPORTS_MCP_SERVER_PATH` (all optional overrides)
5. Deploy, then point your Twilio number's webhook at `https://<your-render-domain>/sms` (see the main [README](README.md#configuring-the-twilio-webhook)).

### Why `--workers 1`?

Chat sessions are kept in an in-memory Python dict, not a database (see [README: Session Model & Limitations](README.md#session-model--limitations)). Running more than one Gunicorn worker would split each phone number's conversation across separate, inconsistent processes. `--threads 4` still lets one worker serve multiple concurrent requests, since Flask releases the GIL during network I/O (Gemini/ESPN/Twilio calls).

---

## Generic self-hosted deployment (Docker / any VPS)

Render isn't required — anything that can run Gunicorn and expose a public HTTPS URL works.

### Minimal Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "120"]
```

```bash
docker build -t sms-to-gemini-twilio .
docker run -d \
  -p 5000:5000 \
  -e API_KEY=your_key \
  -e TWILIO_ACCOUNT_SID=your_sid \
  -e TWILIO_AUTH_TOKEN=your_token \
  --name sms-to-gemini \
  sms-to-gemini-twilio
```

### Bare VPS (systemd + Gunicorn)

```bash
cd /opt/sms-to-gemini-twilio/Twilio
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Example `/etc/systemd/system/sms-to-gemini.service`:

```ini
[Unit]
Description=SMS to Gemini (Twilio)
After=network.target

[Service]
WorkingDirectory=/opt/sms-to-gemini-twilio/Twilio
EnvironmentFile=/opt/sms-to-gemini-twilio/Twilio/.env
ExecStart=/opt/sms-to-gemini-twilio/Twilio/.venv/bin/gunicorn app:app --bind 0.0.0.0:5000 --workers 1 --threads 4 --timeout 120
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now sms-to-gemini
```

Whichever route you use, put a reverse proxy with a valid TLS certificate (Caddy, Nginx + Let's Encrypt, or a platform's managed TLS) in front, since Twilio requires HTTPS webhook URLs. Then point your Twilio number's webhook at `https://your-domain/sms`.

### Health checks

Every deployment target above can point its health check at `GET /health`, which returns `{"status": "ok"}` with HTTP 200 as soon as the app has loaded (it does not verify Gemini/Twilio connectivity — just that the process is up).
