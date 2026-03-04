import asyncio
import difflib
import io
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

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
MODEL_ID = os.getenv("GEMINI_MODEL_ID", "gemini-3.flash-preview")

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
SPORTS_MCP_SERVER_PATH = os.getenv(
    "SPORTS_MCP_SERVER_PATH",
    str(Path(__file__).resolve().with_name("sports_mcp_server.py")),
)
SPORTS_MCP_PYTHON = os.getenv("SPORTS_MCP_PYTHON", sys.executable)

LEAGUE_KEYWORDS: Dict[str, List[str]] = {
    "mlb": ["mlb", "baseball"],
    "nhl": ["nhl", "hockey"],
    "nba": ["nba", "basketball"],
    "nfl": ["nfl", "football"],
}

LEAGUE_TEAM_NAMES: Dict[str, List[str]] = {
    "mlb": [
        "diamondbacks", "braves", "orioles", "red sox", "cubs", "white sox",
        "reds", "guardians", "rockies", "tigers", "astros", "royals", "angels",
        "dodgers", "marlins", "brewers", "twins", "mets", "yankees", "athletics",
        "phillies", "pirates", "padres", "giants", "mariners", "cardinals",
        "rays", "rangers", "blue jays", "nationals",
    ],
    "nhl": [
        "ducks", "utah hockey club", "bruins", "sabres", "flames", "hurricanes",
        "blackhawks", "avalanche", "blue jackets", "stars", "red wings", "oilers",
        "panthers", "kings", "wild", "canadiens", "predators", "devils",
        "islanders", "rangers", "senators", "flyers", "penguins", "kraken",
        "sharks", "blues", "lightning", "maple leafs", "canucks", "golden knights",
        "capitals", "jets",
    ],
    "nba": [
        "hawks", "celtics", "nets", "hornets", "bulls", "cavaliers", "mavericks",
        "nuggets", "pistons", "warriors", "rockets", "pacers", "clippers",
        "lakers", "grizzlies", "heat", "bucks", "timberwolves", "pelicans",
        "knicks", "thunder", "magic", "sixers", "76ers", "suns", "trail blazers",
        "blazers", "kings", "spurs", "raptors", "jazz", "wizards",
    ],
    "nfl": [
        "cardinals", "falcons", "ravens", "bills", "panthers", "bears", "bengals",
        "browns", "cowboys", "broncos", "lions", "packers", "texans", "colts",
        "jaguars", "chiefs", "raiders", "chargers", "rams", "dolphins",
        "vikings", "patriots", "saints", "giants", "jets", "eagles", "steelers",
        "49ers", "niners", "seahawks", "buccaneers", "bucs", "titans",
        "commanders",
    ],
}

GENERIC_SPORTS_KEYWORDS = [
    "sports scores",
    "sports score",
    "scoreboard",
    "live scores",
    "games today",
    "score",
    "scores",
    "game",
    "games",
    "tonight",
    "matchup",
    "matchups",
    "play",
    "playing",
    "final",
    "standings",
    "schedule",
    "won",
    "lost",
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


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()


def _build_ngrams(text: str, max_words: int = 3) -> List[str]:
    normalized = _normalize_text(text)
    tokens = [token for token in normalized.split() if token]
    ngrams: List[str] = []
    for n in range(1, max_words + 1):
        for start in range(0, max(0, len(tokens) - n + 1)):
            ngram = " ".join(tokens[start:start + n])
            if len(ngram) >= 3:
                ngrams.append(ngram)
    return ngrams


def _contains_exact_or_fuzzy_match(ngrams: Sequence[str], terms: Sequence[str], cutoff: float = 0.84) -> bool:
    normalized_terms = [_normalize_text(term) for term in terms if term]

    for ngram in ngrams:
        for term in normalized_terms:
            if ngram == term or ngram in term or term in ngram:
                return True
            if difflib.SequenceMatcher(None, ngram, term).ratio() >= cutoff:
                return True
    return False


def detect_requested_leagues_and_team_intent(text: str) -> Tuple[List[str], bool]:
    ngrams = _build_ngrams(text, max_words=3)
    if not ngrams:
        return [], False

    requested: List[str] = []
    team_intent = False

    for league in ("mlb", "nhl", "nba", "nfl"):
        league_terms = LEAGUE_KEYWORDS[league]
        team_terms = LEAGUE_TEAM_NAMES[league]

        has_league_match = _contains_exact_or_fuzzy_match(ngrams, league_terms, cutoff=0.82)
        has_team_match = _contains_exact_or_fuzzy_match(ngrams, team_terms, cutoff=0.84)

        if has_league_match or has_team_match:
            requested.append(league)
        if has_team_match:
            team_intent = True

    if requested:
        unique_requested: List[str] = []
        for league in ("mlb", "nhl", "nba", "nfl"):
            if league in requested:
                unique_requested.append(league)
        return unique_requested, team_intent

    has_generic_sports_intent = _contains_exact_or_fuzzy_match(
        ngrams,
        GENERIC_SPORTS_KEYWORDS,
        cutoff=0.83,
    )
    if has_generic_sports_intent:
        return ["mlb", "nhl", "nba", "nfl"], False

    return [], False


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


async def _get_live_sports_scores_from_mcp_async(leagues: Sequence[str], query: str = "") -> str:
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
                {"leagues": leagues_arg, "query": query},
            )

    return _extract_mcp_text(tool_result)


def get_live_sports_scores_from_mcp(leagues: Sequence[str], query: str = "") -> str:
    try:
        return asyncio.run(_get_live_sports_scores_from_mcp_async(leagues, query=query))
    except Exception as exc:
        logging.error("Failed to fetch sports scores from MCP: %s", exc)
        raise


def get_live_sports_scores(leagues: Sequence[str], query: str = "") -> str:
    try:
        return get_live_sports_scores_from_mcp(leagues, query=query)
    except Exception:
        return (
            "Unable to retrieve live scores right now because the sports MCP service is unavailable."
        )


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

    requested_leagues, has_team_intent = detect_requested_leagues_and_team_intent(prompt)
    if requested_leagues:
        team_query = prompt if has_team_intent else ""
        live_scores = get_live_sports_scores(requested_leagues, query=team_query)
        requested_league_labels = ", ".join(league.upper() for league in requested_leagues)
        prompt += (
            f"\n\nHere are the current {requested_league_labels} scores "
            "from ESPN via the sports MCP server:\n"
            f"{live_scores}"
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
