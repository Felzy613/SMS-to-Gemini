# SMS to Gemini (Twilio Version)

This project provides a seamless bridge between SMS (via Twilio) and Google Gemini, enabling you to interact with advanced AI through text messages. It includes built-in support for live sports scores via a custom MCP server and Google Search integration for real-time information.

## Features

- **AI-Powered Conversations**: Powered by Google Gemini 2.5 Flash.
- **Real-Time Sports Scores**: Integrated MCP server fetching live data from ESPN for MLB, NHL, NBA, and NFL.
- **Google Search Integration**: Gemini can use Google Search to provide up-to-date answers.
- **Image Support**: Send images via MMS to Gemini for visual analysis.
- **Session Management**: Maintains separate chat histories for each phone number.
- **Easy Deployment**: Pre-configured for Render and other cloud platforms.

---

## Prerequisites

1. **Google AI Studio API Key**: Get it from [aistudio.google.com](https://aistudio.google.com/).
2. **Twilio Account**: A Twilio phone number with SMS/MMS capabilities.
3. **Python 3.10+**: Ensure Python is installed on your system.

---

## Setup Instructions

### 1. Clone the Repository
```bash
git clone <your-repo-url>
cd SMS-to-Gemini-Twilio/Twilio
```

### 2. Install Dependencies
It's recommended to use a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Create a `.env` file in the `Twilio/` directory (or set these in your deployment dashboard):

```env
API_KEY=your_google_gemini_api_key
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
GEMINI_MODEL_ID=gemini-2.5-flash  # Optional
LOG_LEVEL=INFO                    # Optional
```

### 4. Local Testing (Optional)
To test locally, you can use [Ngrok](https://ngrok.com/) to expose your local server to the internet:
1. Start the Flask app:
   ```bash
   python app.py
   ```
2. In a new terminal, run Ngrok:
   ```bash
   ngrok http 5000
   ```
3. Copy the `https://...` URL provided by Ngrok.

### 5. Configure Twilio Webhook
1. Go to your [Twilio Console](https://www.twilio.com/console).
2. Navigate to **Phone Numbers** > **Manage** > **Active Numbers**.
3. Click on your Twilio number.
4. Scroll down to the **Messaging** section.
5. Under **A MESSAGE COMES IN**, select **Webhook** and paste your URL (e.g., `https://your-app.onrender.com/sms` or your Ngrok URL followed by `/sms`).
6. Ensure the method is set to `HTTP POST`.
7. Click **Save**.

---

## Deployment (Render)

This project is pre-configured for deployment on [Render](https://render.com/).

1. Connect your GitHub repository to Render.
2. Create a new **Web Service**.
3. Use the following settings:
   - **Runtime**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
4. Add your **Environment Variables** (API_KEY, TWILIO_ACCOUNT_SID, etc.) in the Render dashboard.

---

## How it Works

1. **Inbound SMS**: Twilio receives a message and sends a POST request to the `/sms` endpoint.
2. **Intent Detection**: The script analyzes the message for sports-related keywords.
3. **Tools & Search**: 
   - If sports are detected, it queries the local `sports_mcp_server.py`.
   - It always has access to Google Search for general queries.
4. **Gemini Processing**: The combined context (message, search results, sports scores, images) is sent from `sms_gemini.py` to Gemini.
5. **Outbound SMS**: The AI's response is formatted and sent back to the user via Twilio's TwiML.

## License
MIT
