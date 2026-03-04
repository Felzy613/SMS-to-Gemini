import difflib
import logging
import os
import re
from typing import Dict, List, Sequence

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

TEAM_QUERY_STOPWORDS = {
    "mlb", "nhl", "nba", "nfl", "sports", "sport", "score", "scores", "game",
    "games", "today", "tonight", "yesterday", "tomorrow", "live", "latest", "current",
    "show", "me", "the", "a", "an", "for", "and", "or", "of", "in", "on", "with",
    "who", "is", "are", "was", "were", "did", "does", "do", "what", "whats", "update",
    "updates", "standings", "schedule", "matchup", "matchups", "play", "playing",
    "baseball", "hockey", "basketball", "football",
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()



def build_ngrams(tokens: Sequence[str], max_words: int = 3) -> List[str]:
    ngrams: List[str] = []
    for n in range(1, max_words + 1):
        for start in range(0, max(0, len(tokens) - n + 1)):
            ngram = " ".join(tokens[start:start + n]).strip()
            if len(ngram) >= 3:
                ngrams.append(ngram)
    return ngrams



def normalize_leagues(leagues: str) -> List[str]:
    raw_value = normalize_text(leagues or "all")
    if raw_value in {"all", "*"}:
        return list(LEAGUE_CONFIG.keys())

    requested: List[str] = []
    tokens = [part.strip() for part in raw_value.replace(";", ",").split(",") if part.strip()]

    for token in tokens:
        if token in LEAGUE_CONFIG:
            requested.append(token)
            continue
        alias_target = LEAGUE_ALIASES.get(token)
        if alias_target:
            requested.append(alias_target)
            continue

        candidates = list(LEAGUE_CONFIG.keys()) + list(LEAGUE_ALIASES.keys())
        match = difflib.get_close_matches(token, candidates, n=1, cutoff=0.8)
        if not match:
            continue

        matched = match[0]
        requested.append(LEAGUE_ALIASES.get(matched, matched))

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



def build_team_query_ngrams(query: str) -> List[str]:
    normalized = normalize_text(query)
    if not normalized:
        return []

    tokens = [
        token
        for token in normalized.split()
        if token and token not in TEAM_QUERY_STOPWORDS and (len(token) >= 3 or token.isdigit())
    ]
    if not tokens:
        return []

    return build_ngrams(tokens, max_words=3)



def extract_event_team_terms(event: dict) -> List[str]:
    competitions = event.get("competitions", [])
    if not competitions:
        return []

    competition = competitions[0]
    competitors = competition.get("competitors", [])
    team_terms: List[str] = []

    for competitor in competitors:
        team = competitor.get("team", {})
        for field in ("shortDisplayName", "displayName", "name", "abbreviation"):
            value = team.get(field)
            if isinstance(value, str) and value.strip():
                normalized = normalize_text(value)
                if normalized:
                    team_terms.append(normalized)

    unique_terms: List[str] = []
    seen = set()
    for term in team_terms:
        if term not in seen:
            seen.add(term)
            unique_terms.append(term)

    return unique_terms



def event_matches_team_query(event: dict, query_ngrams: Sequence[str]) -> bool:
    if not query_ngrams:
        return True

    team_terms = extract_event_team_terms(event)
    if not team_terms:
        return False

    for query_term in query_ngrams:
        for team_term in team_terms:
            if query_term == team_term or query_term in team_term or team_term in query_term:
                return True
            if difflib.SequenceMatcher(None, query_term, team_term).ratio() >= 0.82:
                return True

    return False



def fetch_league_scores(league_key: str, query: str = "") -> str:
    league_label = LEAGUE_CONFIG[league_key]["label"]
    url = build_scoreboard_url(league_key)
    query_ngrams = build_team_query_ngrams(query)

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
        if query_ngrams and not event_matches_team_query(event, query_ngrams):
            continue

        formatted_event = format_event(event)
        if formatted_event:
            lines.append(f"- {formatted_event}")

    if not lines and query_ngrams:
        return f"{league_label}: No matching team games found today for \"{query.strip()}\"."
    if not lines:
        return f"{league_label}: No score data is available right now."

    return f"{league_label}:\n" + "\n".join(lines)


@mcp.tool()
def get_live_scores(leagues: str = "all", query: str = "") -> str:
    """Get live ESPN scoreboard data for mlb, nhl, nba, and nfl."""
    league_keys = normalize_leagues(leagues)
    if not league_keys:
        return "No supported leagues requested. Use one or more of: mlb, nhl, nba, nfl."

    blocks = [fetch_league_scores(league_key, query=query) for league_key in league_keys]
    return "\n\n".join(blocks)


if __name__ == "__main__":
    mcp.run()
