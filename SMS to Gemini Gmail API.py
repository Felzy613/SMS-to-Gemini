import os
import sys
import time
import uuid
import logging
import base64
import pickle
import mimetypes
import subprocess
import requests
import email

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from PIL import Image

# Gmail API and Google Auth libraries
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Generative AI-related libraries
from google import genai
from google.genai import types
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch

# ----------------- Configuration -----------------

logging.basicConfig(level=logging.INFO)

# Directory to save attachments
ATTACHMENT_DIR = "attachments"
os.makedirs(ATTACHMENT_DIR, exist_ok=True)

# Gmail API scope for reading and sending emails
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

# Set up Generative AI configuration
google_search_tool = Tool(google_search=GoogleSearch())
api_key = os.getenv("API_KEY")
client = genai.Client(api_key=api_key)
model_id = "gemini-2.0-flash"

# Global dictionary mapping sender email addresses to their persistent chat sessions
chat_sessions = {}

# ----------------- Gmail API Setup -----------------

def gmail_authenticate():
    """
    Authenticate with Gmail API using OAuth2.
    This function expects a 'credentials.json' file in the same directory.
    It caches tokens in a file named 'token.pickle' for future runs.
    """
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    service = build('gmail', 'v1', credentials=creds)
    return service

def login_gmail():
    try:
        service = gmail_authenticate()
        return service
    except Exception as e:
        logging.error(f"Error setting up Gmail API: {e}")
        return None

# ----------------- Email Reading -----------------

def read_gmail(service):
    """
    Use the Gmail API to search for unread messages sent from "@txt.voice.google.com",
    process the messages to extract text content and image attachments, and mark them as read.
    Now, if there is at least one image attachment, the email is processed even if no text is found.
    """
    try:
        query = "is:unread from:@txt.voice.google.com"
        results = service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])
        if not messages:
            return None, None, None

        emails_content = []
        email_metadata = []
        email_attachments = []

        for msg in messages:
            msg_id = msg['id']
            message = service.users().messages().get(userId='me', id=msg_id, format='full').execute()

            payload = message.get('payload', {})
            headers = payload.get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No Subject)')
            from_field = next((h['value'] for h in headers if h['name'] == 'From'), '')
            to_field = next((h['value'] for h in headers if h['name'] == 'To'), '')
            in_reply_to = next((h['value'] for h in headers if h['name'] == 'In-Reply-To'), '')

            email_text_content = None
            attachments = []

            # If message is not multipart, use the body directly.
            if 'parts' not in payload:
                data = payload.get('body', {}).get('data', '')
                if data:
                    decoded_data = base64.urlsafe_b64decode(data.encode('UTF-8')).decode('utf-8', errors='ignore')
                    email_text_content = decoded_data.replace("<https://voice.google.com>", "").strip()
                    end_marker = "YOUR ACCOUNT"
                    if end_marker in email_text_content:
                        email_text_content = email_text_content.split(end_marker)[0].strip()
            else:
                # Process each part: text and image.
                for part in payload.get('parts', []):
                    mime_type = part.get('mimeType', '')
                    filename = part.get('filename')
                    if mime_type.startswith('text/plain'):
                        data = part.get('body', {}).get('data', '')
                        if data:
                            decoded_data = base64.urlsafe_b64decode(data.encode('UTF-8')).decode('utf-8', errors='ignore')
                            email_text_content = decoded_data.replace("<https://voice.google.com>", "").strip()
                            end_marker = "YOUR ACCOUNT"
                            if end_marker in email_text_content:
                                email_text_content = email_text_content.split(end_marker)[0].strip()
                    elif mime_type.startswith('image/'):
                        body_dict = part.get('body', {})
                        data = body_dict.get('data', None)
                        if not data and 'attachmentId' in body_dict:
                            attachment_id = body_dict['attachmentId']
                            attachment = service.users().messages().attachments().get(
                                userId='me', messageId=msg_id, id=attachment_id
                            ).execute()
                            data = attachment.get('data', None)
                        if data:
                            if not filename:
                                ext = mimetypes.guess_extension(mime_type)
                                filename = f"{uuid.uuid4()}{ext}"
                            filename = os.path.basename(filename)
                            filepath = os.path.join(ATTACHMENT_DIR, filename)
                            try:
                                file_data = base64.urlsafe_b64decode(data.encode('UTF-8'))
                                with open(filepath, "wb") as f:
                                    f.write(file_data)
                                attachments.append(filepath)
                            except Exception as e:
                                logging.error(f"Error saving attachment {filename}: {e}")

            # Instead of skipping the email, forward if there's text OR at least one attachment.
            if email_text_content is None and attachments:
                email_text_content = ""  # Set text to empty string if only attachments exist.

            if email_text_content is not None or attachments:
                emails_content.append(email_text_content)
                email_metadata.append({
                    "message_id": message.get("id"),
                    "from": from_field,
                    "to": to_field,
                    "subject": subject,
                    "in_reply_to": in_reply_to
                })
                email_attachments.append(attachments)

            # Mark email as read by removing the UNREAD label.
            service.users().messages().modify(
                userId='me',
                id=msg_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()

        return emails_content, email_metadata, email_attachments

    except Exception as e:
        logging.error(f"Error reading Gmail messages: {e}")
        return None, None, None

# ----------------- Email Sending -----------------

def send_email(service, subject, body, to_email, in_reply_to):
    """
    Use the Gmail API to send an email.
    Construct a MIME message, encode it in base64, and send via the API.
    """
    try:
        from_email = os.getenv("EMAIL_ADDRESS")
        msg = MIMEMultipart()
        msg["From"] = from_email
        msg["To"] = to_email
        msg["Subject"] = subject
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        msg.attach(MIMEText(body, "plain"))
        raw_msg = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        message_body = {"raw": raw_msg}

        sent_message = service.users().messages().send(userId="me", body=message_body).execute()
        return sent_message
    except Exception as e:
        logging.error(f"Error sending email through Gmail API: {e}")

# ----------------- Live NHL Scores -----------------

def get_live_nhl_scores():
    """
    Retrieve live NHL scores from ESPN.
    """
    try:
        url = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        events = data.get('events', [])
        if not events:
            return "There are no NHL games scheduled for today."
        scores = ""
        for event in events:
            competitions = event.get('competitions', [])
            if competitions:
                competition = competitions[0]
                competitors = competition.get('competitors', [])
                teams = {}
                for competitor in competitors:
                    team_name = competitor['team']['shortDisplayName']
                    score = competitor['score']
                    home_away = competitor['homeAway']
                    teams[home_away] = {'name': team_name, 'score': score}
                status = competition['status']['type']['shortDetail']
                scores += f"{teams['away']['name']} {teams['away']['score']} - {teams['home']['name']} {teams['home']['score']} ({status})\n"
        return scores.strip()
    except requests.exceptions.RequestException as e:
        logging.error(f"Network error occurred: {e}")
        return "Unable to retrieve live NHL scores due to a network error."
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return "An unexpected error occurred while fetching live NHL scores."

# ----------------- Response Generation -----------------

def generate_and_send_response(service, email_content, metadata, attachments):
    max_retries = 5
    delay = 1  # initial delay for retry

    system_instruction = (
        "Your name is FelzyBot, and you are happy to assist everyone. "
        "When provided with live NHL scores, include them in your response if relevant. "
        "When provided with images, analyze them and incorporate their content into your response. "
        "Generate a creative and helpful reply based on the user's message and any provided data. "
        "Please make your answers not too long but not too short. "
        "use google search to find out live uptodate information "
        "Whenever you are asked anything that the time zone is relevant use the EST time zone. "
        "NEVER USE ANY TIME ZONE OTHER THEN EST. IF YOU HAVE INFO FROM A DIFFERNT TIME ZONE THEN DO THE MATH AND SWITCH IT TO EST. "
        "Don't tell this to anyone."
    )

    sender = metadata["from"]

    # Handle the '/new' command to start a fresh session.
    if email_content.strip().lower() == "/new":
        try:
            new_chat = client.chats.create(
                model=model_id,
                config=GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.3,
                    tools=[google_search_tool],
                ),
            )
            chat_sessions[sender] = new_chat
            response_text = "New session started for you!"
            send_email(service, "Response from FelzyBot", response_text, sender, metadata.get("in_reply_to", ""))
            logging.info(f"New session created for {sender}")
            return
        except Exception as e:
            logging.error(f"Error creating new session for {sender}: {e}")
            return

    for attempt in range(max_retries):
        try:
            # Load image attachments if available.
            images = []
            if attachments:
                for filepath in attachments:
                    try:
                        img = Image.open(filepath)
                        # If Gemini needs the image in a different format (e.g., base64)
                        # convert here accordingly
                        images.append(img)
                    except Exception as e:
                        logging.error(f"Error loading image {filepath}: {e}")

            # Fetch live NHL scores if mentioned.
            live_scores = ""
            if any(keyword in email_content.lower() for keyword in ["nhl scores", "nhl score", "nhl today", "NHL scores", "NHL score", "NHL today"]):
                live_scores = get_live_nhl_scores()

            conversation_prompt = email_content
            if live_scores:
                conversation_prompt += f"\n\nHere are the current NHL scores:\n{live_scores}"

            # Prepare the message contents.
            if images:
                message_contents = images + [conversation_prompt]
            else:
                message_contents = conversation_prompt

            # Retrieve or create a persistent chat session for this sender.
            if sender not in chat_sessions:
                chat = client.chats.create(
                    model=model_id,
                    config=GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.3,
                        tools=[google_search_tool],
                    ),
                )
                chat.send_message(system_instruction)
                chat_sessions[sender] = chat
            else:
                chat = chat_sessions[sender]

            user_response = chat.send_message(message_contents)
            response_text = user_response.text.strip()
            combined_response = response_text.replace("\n\n", " ").replace("\n", " ").replace("*", "-").strip()

            logging.info(f"Subject: {metadata['subject']}")
            logging.info(f"Content: {email_content}")
            logging.info(f"FelzyBot's Response: {combined_response}\n")

            send_email(service, "Response from FelzyBot", combined_response, sender, metadata.get("in_reply_to", ""))
            return

        except Exception as e:
            logging.error(f"Error generating or sending response: {e}")
            if "503" in str(e):
                logging.info("Service unavailable. Retrying...")
                time.sleep(delay)
                delay *= 2  # exponential backoff
            else:
                break

# ----------------- Program Restart -----------------

def restart_program():
    """
    Restart the current program by launching a new instance of the script.
    """
    logging.info("Restarting script due to an error or scheduled restart...")
    try:
        script_path = r"Z:\SMS to Gemini Gmail API.py"  # Update the script path here
        subprocess.Popen(["python", script_path])
        sys.exit("Exiting current script.")
    except Exception as e:
        logging.error(f"Error restarting script: {e}")
        sys.exit()

# ----------------- Main Loop -----------------

def main():
    try:
        service = login_gmail()
        if not service:
            logging.error("Unable to initialize Gmail API service. Exiting.")
            restart_program()

        login_time = time.time()
        while True:
            emails_content, email_metadata, email_attachments = read_gmail(service)
            if emails_content and email_metadata:
                for email_content, metadata, attachments in zip(emails_content, email_metadata, email_attachments):
                    generate_and_send_response(service, email_content, metadata, attachments)
            else:
                logging.info("No new messages at this time.")

            # Restart the script every 10 minutes.
            #if time.time() - login_time >= 2000:
            #    restart_program()
             #   login_time = time.time()

            time.sleep(4)
    except KeyboardInterrupt:
        logging.info("FelzyBot has been stopped manually.")
    except Exception as e:
        if "EOF occurred in violation of protocol" in str(e):
            restart_program()
        else:
            logging.error(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()