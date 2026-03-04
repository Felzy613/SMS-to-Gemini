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
   - `GEMINI_MODEL_ID` (optional, default: `gemini-2.5-flash`)
   - `SPORTS_MCP_PYTHON` and `SPORTS_MCP_SERVER_PATH` (optional overrides)
4. Point Twilio webhook to: `https://<your-render-domain>/sms`
