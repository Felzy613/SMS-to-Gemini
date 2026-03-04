# Deployment Guide

## Render (Python Flask)

This project is ready for Render with:
- `app.py` (stable module entrypoint for Gunicorn)
- `Procfile`
- `render.yaml`

### Steps

1. Create a new **Web Service** from this repo.
2. Render will use:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
3. Set environment variables:
   - `API_KEY` (required)
   - `TWILIO_ACCOUNT_SID` (required for media/image download)
   - `TWILIO_AUTH_TOKEN` (required for media/image download)
   - `GEMINI_MODEL_ID` (optional, default: `gemini-3-flash-preview`)
   - `SPORTS_SOURCE` (optional: `mcp` default, or `direct`)
   - `SPORTS_MCP_PYTHON` and `SPORTS_MCP_SERVER_PATH` (optional overrides)
4. Point Twilio webhook to: `https://<your-render-domain>/sms`

## Cloudflare Workers

Flask + MCP stdio subprocesses are not supported on Workers runtime, so a Worker-native implementation is included at:
- `cloudflare-worker/src/worker.js`
- `cloudflare-worker/wrangler.toml`

### Steps

1. Install Wrangler (if needed):
   - `npm install -g wrangler`
2. Deploy from the worker folder:
   - `cd cloudflare-worker`
   - `wrangler secret put API_KEY`
   - `wrangler secret put TWILIO_ACCOUNT_SID`
   - `wrangler secret put TWILIO_AUTH_TOKEN`
   - `wrangler deploy`
3. Set Twilio webhook URL to: `https://<your-worker-domain>/sms`

### Worker behavior notes

- Uses ESPN directly for MLB/NHL/NBA/NFL scores.
- Uses Gemini REST API directly.
- Stateless by design (`/new` returns a stateless-session message).

