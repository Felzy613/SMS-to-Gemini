const SYSTEM_INSTRUCTION =
  "When provided with live sports scores, include them in your response if relevant. " +
  "When provided with images, analyze them carefully and incorporate their content into your response. " +
  "Generate creative and helpful replies based on the user's message and any provided data. " +
  "Keep your answers concise but informative - not too long but not too short. " +
  "For time-sensitive questions, always use EST time zone unless the user specifies otherwise. " +
  "Be conversational and friendly while maintaining accuracy and helpfulness.";

const LEAGUE_KEYWORDS = {
  mlb: ["mlb", "baseball"],
  nhl: ["nhl", "hockey"],
  nba: ["nba", "basketball"],
  nfl: ["nfl", "football"],
};

const LEAGUE_ENDPOINTS = {
  mlb: { sport: "baseball", league: "mlb", label: "MLB" },
  nhl: { sport: "hockey", league: "nhl", label: "NHL" },
  nba: { sport: "basketball", league: "nba", label: "NBA" },
  nfl: { sport: "football", league: "nfl", label: "NFL" },
};

const GENERIC_SPORTS_KEYWORDS = [
  "sports scores",
  "sports score",
  "scoreboard",
  "live scores",
  "games today",
];

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/health") {
      return jsonResponse({ status: "ok" }, 200);
    }

    if (request.method === "POST" && url.pathname === "/sms") {
      return handleSmsWebhook(request, env);
    }

    return new Response("Not Found", { status: 404 });
  },
};

async function handleSmsWebhook(request, env) {
  const formBody = await request.text();
  const form = new URLSearchParams(formBody);

  const incomingText = (form.get("Body") || "").trim();
  const numMedia = Number.parseInt(form.get("NumMedia") || "0", 10);

  if (!incomingText && numMedia <= 0) {
    return twimlResponse("Send a text question or an image to get started.");
  }

  if (incomingText.toLowerCase() === "/new") {
    return twimlResponse("Cloudflare Worker mode is stateless, so each request is already a new session.");
  }

  let prompt = incomingText;
  const images = await extractTwilioImages(form, numMedia, env);

  if (!prompt && images.length > 0) {
    prompt =
      "The user sent one or more images with no text. " +
      "Describe what you see and provide a helpful response.";
  }

  const requestedLeagues = detectRequestedLeagues(prompt);
  if (requestedLeagues.length > 0) {
    const liveScores = await getLiveSportsScores(requestedLeagues);
    const labels = requestedLeagues.map((league) => league.toUpperCase()).join(", ");
    prompt += `\n\nHere are the current ${labels} scores from ESPN:\n${liveScores}`;
  }

  try {
    const reply = await generateGeminiReply(prompt, images, env);
    return twimlResponse(normalizeResponse(reply));
  } catch (error) {
    console.error("Gemini response error:", error);
    return twimlResponse("I ran into an error processing that message. Please try again in a moment.");
  }
}

function detectRequestedLeagues(text) {
  const lowered = (text || "").toLowerCase();
  const requested = [];

  for (const [league, keywords] of Object.entries(LEAGUE_KEYWORDS)) {
    if (keywords.some((keyword) => lowered.includes(keyword))) {
      requested.push(league);
    }
  }

  if (requested.length > 0) {
    return requested;
  }

  if (GENERIC_SPORTS_KEYWORDS.some((keyword) => lowered.includes(keyword))) {
    return Object.keys(LEAGUE_ENDPOINTS);
  }

  return [];
}

async function getLiveSportsScores(leagues) {
  const blocks = [];

  for (const leagueKey of leagues) {
    const config = LEAGUE_ENDPOINTS[leagueKey];
    if (!config) {
      continue;
    }

    const url =
      "https://site.api.espn.com/apis/site/v2/sports/" +
      `${config.sport}/${config.league}/scoreboard`;

    try {
      const response = await fetch(url, { method: "GET" });
      if (!response.ok) {
        blocks.push(`${config.label}: Unable to retrieve scores (HTTP ${response.status}).`);
        continue;
      }

      const payload = await response.json();
      const events = Array.isArray(payload.events) ? payload.events : [];

      if (events.length === 0) {
        blocks.push(`${config.label}: No games scheduled today.`);
        continue;
      }

      const lines = [];
      for (const event of events) {
        const line = formatEspnEvent(event);
        if (line) {
          lines.push(`- ${line}`);
        }
      }

      if (lines.length === 0) {
        blocks.push(`${config.label}: No score data is available right now.`);
      } else {
        blocks.push(`${config.label}:\n${lines.join("\n")}`);
      }
    } catch (error) {
      console.error(`Score fetch error for ${config.label}:`, error);
      blocks.push(`${config.label}: Unable to retrieve scores due to a network error.`);
    }
  }

  if (blocks.length === 0) {
    return "No supported leagues requested. Use one or more of: mlb, nhl, nba, nfl.";
  }

  return blocks.join("\n\n");
}

function formatEspnEvent(event) {
  const competitions = Array.isArray(event.competitions) ? event.competitions : [];
  if (competitions.length === 0) {
    return "";
  }

  const competition = competitions[0];
  const competitors = Array.isArray(competition.competitors) ? competition.competitors : [];
  let home = null;
  let away = null;

  for (const competitor of competitors) {
    const teamName = competitor?.team?.shortDisplayName || "Unknown";
    const score = competitor?.score || "0";
    const side = competitor?.homeAway;

    if (side === "home") {
      home = { name: teamName, score };
    } else if (side === "away") {
      away = { name: teamName, score };
    }
  }

  if (!home || !away) {
    return "";
  }

  const status =
    competition?.status?.type?.shortDetail ||
    event?.status?.type?.shortDetail ||
    "Status unavailable";

  return `${away.name} ${away.score} - ${home.name} ${home.score} (${status})`;
}

async function extractTwilioImages(form, numMedia, env) {
  if (!env.TWILIO_ACCOUNT_SID || !env.TWILIO_AUTH_TOKEN || numMedia <= 0) {
    return [];
  }

  const auth =
    "Basic " + btoa(`${env.TWILIO_ACCOUNT_SID}:${env.TWILIO_AUTH_TOKEN}`);

  const images = [];

  for (let index = 0; index < numMedia; index += 1) {
    const mediaUrl = form.get(`MediaUrl${index}`);
    const mediaType = form.get(`MediaContentType${index}`) || "";

    if (!mediaUrl || !mediaType.startsWith("image/")) {
      continue;
    }

    try {
      const response = await fetch(mediaUrl, {
        method: "GET",
        headers: { Authorization: auth },
      });
      if (!response.ok) {
        continue;
      }
      const content = await response.arrayBuffer();
      images.push({
        mimeType: mediaType,
        data: arrayBufferToBase64(content),
      });
    } catch (error) {
      console.error(`Failed to download media ${mediaUrl}:`, error);
    }
  }

  return images;
}

async function generateGeminiReply(prompt, images, env) {
  if (!env.API_KEY) {
    throw new Error("Missing API_KEY secret.");
  }

  const model = env.GEMINI_MODEL_ID || "gemini-2.5-flash";
  const endpoint =
    `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}` +
    `:generateContent?key=${encodeURIComponent(env.API_KEY)}`;

  const userParts = [{ text: prompt }];
  for (const image of images) {
    userParts.push({
      inlineData: {
        mimeType: image.mimeType,
        data: image.data,
      },
    });
  }

  const payload = {
    systemInstruction: {
      parts: [{ text: SYSTEM_INSTRUCTION }],
    },
    contents: [
      {
        role: "user",
        parts: userParts,
      },
    ],
    generationConfig: {
      temperature: 0.2,
    },
  };

  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`Gemini API HTTP ${response.status}: ${errorBody}`);
  }

  const body = await response.json();
  const parts = body?.candidates?.[0]?.content?.parts || [];
  const text = parts
    .map((part) => (typeof part?.text === "string" ? part.text : ""))
    .filter(Boolean)
    .join(" ")
    .trim();

  if (!text) {
    return "I could not generate a response right now. Please try again.";
  }

  return text;
}

function normalizeResponse(text) {
  return (text || "").replace(/\*/g, "-").replace(/\s+/g, " ").trim();
}

function twimlResponse(text) {
  const xml =
    '<?xml version="1.0" encoding="UTF-8"?>' +
    `<Response><Message>${escapeXml(text)}</Message></Response>`;
  return new Response(xml, {
    status: 200,
    headers: { "content-type": "application/xml" },
  });
}

function jsonResponse(obj, status) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function arrayBufferToBase64(buffer) {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  const chunkSize = 0x8000;

  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }

  return btoa(binary);
}

function escapeXml(value) {
  return (value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}
