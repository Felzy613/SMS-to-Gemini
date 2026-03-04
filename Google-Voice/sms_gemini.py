import asyncio
import io
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import requests
from flask import Flask, Response, request
from PIL import Image
from twilio.twiml.messaging_response import MessagingResponse

from google import genai
from google.genai.types import GenerateContentConfig, GoogleSearch, Tool

MCP_AVAILABLE = False
ClientSession: Any = None
StdioServerParameters: Any = None
stdio_client: Any = None

try:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    try:
        from mcp import StdioServerParameters
    except Exception:
        from mcp.client.stdio import StdioServerParameters

    MCP_AVAILABLE = True
except Exception:  # pragma: no cover - runtime fallback if mcp isn't installed
    MCP_AVAILABLE = False

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# ----------------- Configuration -----------------

MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))
INITIAL_RETRY_DELAY = float(os.getenv("INITIAL_RETRY_DELAY", "1"))
MODEL_ID = os.getenv("GEMINI_MODEL_ID", "gemini-3-flash-preview")

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
SPORTS_MCP_SERVER_PATH = os.getenv(
    "SPORTS_MCP_SERVER_PATH",
    str(Path(__file__).resolve().with_name("sports_mcp_server.py")),
)
SPORTS_MCP_PYTHON = os.getenv("SPORTS_MCP_PYTHON", sys.executable)
SPORTS_SOURCE = os.getenv("SPORTS_SOURCE", "mcp").strip().lower()

LEAGUE_KEYWORDS: Dict[str, List[str]] = {
    "mlb": ["mlb", "baseball"],
    "nhl": ["nhl", "hockey"],
    "nba": ["nba", "basketball"],
    "nfl": ["nfl", "football"],
}
LEAGUE_ENDPOINTS: Dict[str, Dict[str, str]] = {
    "mlb": {"sport": "baseball", "league": "mlb", "label": "MLB"},
    "nhl": {"sport": "hockey", "league": "nhl", "label": "NHL"},
    "nba": {"sport": "basketball", "league": "nba", "label": "NBA"},
    "nfl": {"sport": "football", "league": "nfl", "label": "NFL"},
}
GENERIC_SPORTS_KEYWORDS = [
    "sports scores",
    "sports score",
    "scoreboard",
    "live scores",
    "games today",
]

api_key = os.getenv("API_KEY")
if not api_key:
    raise RuntimeError("Missing required environment variable: API_KEY")

client = genai.Client(api_key=api_key)
google_search_tool = Tool(google_search=GoogleSearch())

chat_sessions: Dict[str, Any] = {}
app = Flask(__name__)

SYSTEM_INSTRUCTION = (
    "When provided with live sports scores, include them in your response if relevant. "
    "When provided with images, analyze them carefully and incorporate their content into your response. "
    "Generate creative and helpful replies based on the user's message and any provided data. "
    "Keep your answers concise but informative - not too long but not too short. "
    "Use Google Search to find live, up-to-date information when needed. "
    "For time-sensitive questions, always use EST time zone unless the user specifies otherwise. "
    "Be conversational and friendly while maintaining accuracy and helpfulness."
)


# ----------------- Helpers -----------------

def create_chat():
    return client.chats.create(
        model=MODEL_ID,
        config=GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.2,
            tools=[google_search_tool],
        ),
    )


def get_or_create_chat(sender: str):
    if sender not in chat_sessions:
        chat_sessions[sender] = create_chat()
        logging.info("Created new chat session for %s", sender)
    return chat_sessions[sender]


def normalize_response(text: str) -> str:
    cleaned = text.replace("*", "-").strip()
    return " ".join(cleaned.split())


def detect_requested_leagues(text: str) -> List[str]:
    lowered = text.lower()
    requested = []

    for league, keywords in LEAGUE_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            requested.append(league)

    if requested:
        return requested

    if any(keyword in lowered for keyword in GENERIC_SPORTS_KEYWORDS):
        return list(LEAGUE_KEYWORDS.keys())

    return []


def _format_espn_event(event: Dict[str, Any]) -> str:
    competitions = event.get("competitions", [])
    if not competitions:
        return ""

    competition = competitions[0]
    competitors = competition.get("competitors", [])
    home = None
    away = None

    for competitor in competitors:
        team_name = competitor.get("team", {}).get("shortDisplayName", "Unknown")
        score = competitor.get("score", "0")
        side = competitor.get("homeAway")
        if side == "home":
            home = {"name": team_name, "score": score}
        elif side == "away":
            away = {"name": team_name, "score": score}

    if not home or not away:
        return ""

    status = (
        competition.get("status", {}).get("type", {}).get("shortDetail")
        or event.get("status", {}).get("type", {}).get("shortDetail")
        or "Status unavailable"
    )

    return (
        f"{away['name']} {away['score']} - "
        f"{home['name']} {home['score']} ({status})"
    )


def _fetch_league_scores_direct(league_key: str) -> str:
    config = LEAGUE_ENDPOINTS[league_key]
    league_label = config["label"]
    url = (
        "https://site.api.espn.com/apis/site/v2/sports/"
        f"{config['sport']}/{config['league']}/scoreboard"
    )

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        payload = response.json()
    except requests.exceptions.RequestException as exc:
        logging.error("Network error fetching %s scores: %s", league_label, exc)
        return f"{league_label}: Unable to retrieve scores due to a network error."
    except ValueError as exc:
        logging.error("Invalid JSON for %s scores: %s", league_label, exc)
        return f"{league_label}: ESPN returned an invalid response."

    events = payload.get("events", [])
    if not events:
        return f"{league_label}: No games scheduled today."

    lines: List[str] = []
    for event in events:
        event_line = _format_espn_event(event)
        if event_line:
            lines.append(f"- {event_line}")

    if not lines:
        return f"{league_label}: No score data is available right now."

    return f"{league_label}:\n" + "\n".join(lines)


def get_live_sports_scores_direct(leagues: Sequence[str]) -> str:
    league_keys = [league for league in leagues if league in LEAGUE_ENDPOINTS]
    if not league_keys:
        return "No supported leagues requested. Use one or more of: mlb, nhl, nba, nfl."

    return "\n\n".join(_fetch_league_scores_direct(league_key) for league_key in league_keys)


def _extract_mcp_text(tool_result: Any) -> str:
    if getattr(tool_result, "isError", False):
        return "The sports MCP server reported an error."

    text_chunks: List[str] = []
    for item in getattr(tool_result, "content", []) or []:
        text = getattr(item, "text", None)
        if text is None and isinstance(item, dict):
            text = item.get("text")
        if text:
            text_chunks.append(str(text))

    if not text_chunks:
        return "No score data was returned by the sports MCP server."

    return "\n".join(text_chunks).strip()


async def _get_live_sports_scores_from_mcp_async(leagues: Sequence[str]) -> str:
    if (
        not MCP_AVAILABLE
        or ClientSession is None
        or StdioServerParameters is None
        or stdio_client is None
    ):
        raise RuntimeError("Sports MCP support is unavailable because the `mcp` package is not installed.")

    if not os.path.isfile(SPORTS_MCP_SERVER_PATH):
        raise FileNotFoundError(f"Sports MCP server not found: {SPORTS_MCP_SERVER_PATH}")

    server_parameters = StdioServerParameters(
        command=SPORTS_MCP_PYTHON,
        args=[SPORTS_MCP_SERVER_PATH],
    )

    leagues_arg = ",".join(leagues) if leagues else "all"

    async with stdio_client(server_parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tool_result = await session.call_tool(
                "get_live_scores",
                {"leagues": leagues_arg},
            )

    return _extract_mcp_text(tool_result)


def get_live_sports_scores_from_mcp(leagues: Sequence[str]) -> str:
    try:
        return asyncio.run(_get_live_sports_scores_from_mcp_async(leagues))
    except Exception as exc:
        logging.error("Failed to fetch sports scores from MCP: %s", exc)
        raise


def get_live_sports_scores(leagues: Sequence[str]) -> str:
    if SPORTS_SOURCE == "direct":
        return get_live_sports_scores_direct(leagues)

    try:
        return get_live_sports_scores_from_mcp(leagues)
    except Exception:
        logging.info("Falling back to direct ESPN scores because MCP is unavailable.")
        return get_live_sports_scores_direct(leagues)


def fetch_twilio_image(media_url: str) -> Optional[Image.Image]:
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        logging.warning(
            "TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN not set; skipping media download"
        )
        return None

    try:
        response = requests.get(
            media_url,
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            timeout=20,
        )
        response.raise_for_status()

        image = Image.open(io.BytesIO(response.content))
        image.load()  # Detach from the underlying byte stream.
        return image
    except Exception as exc:
        logging.error("Failed to download media from Twilio URL %s: %s", media_url, exc)
        return None


def extract_images_from_twilio(form) -> List[Image.Image]:
    images: List[Image.Image] = []

    try:
        num_media = int(form.get("NumMedia", "0"))
    except ValueError:
        num_media = 0

    for index in range(num_media):
        media_url = form.get(f"MediaUrl{index}")
        media_content_type = form.get(f"MediaContentType{index}", "")

        if not media_url:
            continue
        if not media_content_type.startswith("image/"):
            logging.info("Skipping non-image media (%s): %s", media_content_type, media_url)
            continue

        image = fetch_twilio_image(media_url)
        if image is not None:
            images.append(image)

    return images


def generate_response(sender: str, incoming_text: str, images: List[Image.Image]) -> str:
    delay = INITIAL_RETRY_DELAY

    if incoming_text.strip().lower() == "/new":
        chat_sessions[sender] = create_chat()
        logging.info("Started a new session for %s", sender)
        return "New session started for you!"

    prompt = incoming_text.strip()
    if not prompt and images:
        prompt = (
            "The user sent one or more images with no text. "
            "Describe what you see and provide a helpful response."
        )

    requested_leagues = detect_requested_leagues(prompt)
    if requested_leagues:
        live_scores = get_live_sports_scores(requested_leagues)
        requested_league_labels = ", ".join(league.upper() for league in requested_leagues)
        prompt += (
            f"\n\nHere are the current {requested_league_labels} scores "
            f"from ESPN:\n{live_scores}"
        )

    message_contents: Any = [*images, prompt] if images else prompt

    for attempt in range(MAX_RETRIES):
        try:
            chat = get_or_create_chat(sender)
            model_response = chat.send_message(message_contents)
            response_text = (model_response.text or "").strip()

            if not response_text:
                return "I could not generate a response right now. Please try again."

            final_text = normalize_response(response_text)
            logging.info("From: %s | Prompt: %s | Response: %s", sender, prompt, final_text)
            return final_text

        except Exception as exc:
            logging.error(
                "Error generating response (attempt %s/%s): %s",
                attempt + 1,
                MAX_RETRIES,
                exc,
            )

            if "503" in str(exc) or "rate limit" in str(exc).lower():
                logging.info("Retrying in %s seconds", delay)
                time.sleep(delay)
                delay *= 2
                continue

            break

    return "I ran into an error processing that message. Please try again in a moment."


# ----------------- Twilio Routes -----------------

@app.route("/health", methods=["GET"])
def health_check():
    return {"status": "ok"}, 200


@app.route("/sms", methods=["POST"])
def twilio_sms_webhook():
    sender = request.form.get("From", "unknown")
    incoming_text = (request.form.get("Body") or "").strip()
    images = extract_images_from_twilio(request.form)

    if not incoming_text and not images:
        response_text = "Send a text question or an image to get started."
    else:
        response_text = generate_response(sender, incoming_text, images)

    twiml = MessagingResponse()
    twiml.message(response_text)

    return Response(str(twiml), mimetype="application/xml")


# ----------------- Entrypoint -----------------

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    app.run(host=host, port=port)
