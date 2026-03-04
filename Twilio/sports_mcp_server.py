import logging
import os
from typing import Dict, List

import requests
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

mcp = FastMCP("espn-sports-scores")

LEAGUE_CONFIG: Dict[str, Dict[str, str]] = {
    "mlb": {"sport": "baseball", "league": "mlb", "label": "MLB"},
    "nhl": {"sport": "hockey", "league": "nhl", "label": "NHL"},
    "nba": {"sport": "basketball", "league": "nba", "label": "NBA"},
    "nfl": {"sport": "football", "league": "nfl", "label": "NFL"},
}

LEAGUE_ALIASES = {
    "baseball": "mlb",
    "hockey": "nhl",
    "basketball": "nba",
    "football": "nfl",
}


def normalize_leagues(leagues: str) -> List[str]:
    raw_value = (leagues or "all").strip().lower()
    if raw_value in {"all", "*"}:
        return list(LEAGUE_CONFIG.keys())

    requested = []
    for part in raw_value.replace(";", ",").split(","):
        token = part.strip()
        if not token:
            continue
        if token in LEAGUE_CONFIG:
            requested.append(token)
            continue
        alias_target = LEAGUE_ALIASES.get(token)
        if alias_target:
            requested.append(alias_target)

    unique_requested: List[str] = []
    seen = set()
    for item in requested:
        if item not in seen:
            seen.add(item)
            unique_requested.append(item)

    return unique_requested


def build_scoreboard_url(league_key: str) -> str:
    config = LEAGUE_CONFIG[league_key]
    return (
        "https://site.api.espn.com/apis/site/v2/sports/"
        f"{config['sport']}/{config['league']}/scoreboard"
    )


def format_event(event: dict) -> str:
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


def fetch_league_scores(league_key: str) -> str:
    league_label = LEAGUE_CONFIG[league_key]["label"]
    url = build_scoreboard_url(league_key)

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        payload = response.json()
    except requests.exceptions.RequestException as exc:
        logging.error("Network error for %s: %s", league_label, exc)
        return f"{league_label}: Unable to retrieve scores due to a network error."
    except ValueError as exc:
        logging.error("Invalid JSON for %s: %s", league_label, exc)
        return f"{league_label}: ESPN returned an invalid response."

    events = payload.get("events", [])
    if not events:
        return f"{league_label}: No games scheduled today."

    lines = []
    for event in events:
        formatted_event = format_event(event)
        if formatted_event:
            lines.append(f"- {formatted_event}")

    if not lines:
        return f"{league_label}: No score data is available right now."

    return f"{league_label}:\n" + "\n".join(lines)


@mcp.tool()
def get_live_scores(leagues: str = "all") -> str:
    """Get live ESPN scoreboard data for mlb, nhl, nba, and nfl."""
    league_keys = normalize_leagues(leagues)
    if not league_keys:
        return "No supported leagues requested. Use one or more of: mlb, nhl, nba, nfl."

    blocks = [fetch_league_scores(league_key) for league_key in league_keys]
    return "\n\n".join(blocks)


if __name__ == "__main__":
    mcp.run()
