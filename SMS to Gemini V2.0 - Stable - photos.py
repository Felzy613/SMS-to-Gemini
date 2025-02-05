import os
import imaplib
import email
import mimetypes
from email.message import EmailMessage
from PIL import Image
import io
from google import genai
from google.genai.types import GenerateContentConfig
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import uuid
import logging
import requests

# Clear the screen before starting
os.system('cls' if os.name == 'nt' else 'clear')

# Set up logging to show info messages
logging.basicConfig(level=logging.INFO)

# Configuring the generative AI model
api_key = os.getenv("API_KEY")
client = genai.Client(api_key=api_key)
model_id = "gemini-2.0-flash-exp"

# Directory to save attachments
ATTACHMENT_DIR = "attachments"
os.makedirs(ATTACHMENT_DIR, exist_ok=True)

def login_gmail():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        email_address = os.getenv("EMAIL_ADDRESS")
        email_password = os.getenv("EMAIL_PASSWORD")
        mail.login(email_address, email_password)
        return mail
    except Exception as e:
        print(f"Error logging in to Gmail: {e}")
        return None

def read_gmail(mail):
    try:
        mail.select("inbox")
        search_criteria = '(UNSEEN FROM "@txt.voice.google.com")'
        result, data = mail.search(None, search_criteria)
        mail_ids = data[0].split()
        if not mail_ids:
            return None, None, None
        emails_content = []
        email_metadata = []
        email_attachments = []

        for mail_id in mail_ids:
            result, message_data = mail.fetch(mail_id, "(RFC822)")
            if not message_data or len(message_data) == 0:
                continue
            raw_email = message_data[0][1]
            email_message = email.message_from_bytes(raw_email)
            email_text_content = None
            attachments = []

            for part in email_message.walk():
                content_type = part.get_content_type()
                filename = part.get_filename()
                if part.is_multipart():
                    continue
                if content_type.startswith('image/'):
                    if not filename:
                        ext = mimetypes.guess_extension(content_type)
                        filename = f"{uuid.uuid4()}{ext}"
                    filename = os.path.basename(filename)
                    filepath = os.path.join(ATTACHMENT_DIR, filename)
                    try:
                        with open(filepath, "wb") as f:
                            f.write(part.get_payload(decode=True))
                        attachments.append(filepath)
                    except Exception as e:
                        print(f"Error saving attachment {filename}: {e}")
                elif content_type == 'text/plain':
                    email_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    email_content = email_content.replace("<https://voice.google.com>", "").strip()
                    end_marker = "YOUR ACCOUNT"
                    end_index = email_content.find(end_marker)
                    if end_index != -1:
                        filtered_message = email_content[:end_index].strip()
                        email_text_content = filtered_message
                    else:
                        email_text_content = email_content.strip()

            if email_text_content:
                emails_content.append(email_text_content)
                email_metadata.append({
                    "message_id": email_message["Message-ID"],
                    "from": email.utils.parseaddr(email_message["From"])[1],
                    "to": email_message["To"],
                    "subject": email_message.get("Subject", "(No Subject)"),
                    "in_reply_to": email_message.get("In-Reply-To", "")
                })
                email_attachments.append(attachments)

            # Mark the email as seen
            mail.store(mail_id, '+FLAGS', '\\Seen')

        return emails_content, email_metadata, email_attachments

    except Exception as e:
        print(f"Error reading Gmail: {e}")
        return None, None, None

def send_email(subject, body, to_email, in_reply_to):
    try:
        from_email = os.getenv("EMAIL_ADDRESS")
        from_password = os.getenv("EMAIL_PASSWORD")
        msg = MIMEMultipart()
        msg["From"] = from_email
        msg["To"] = to_email
        msg["Subject"] = subject
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        msg.attach(MIMEText(body, "plain"))
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(from_email, from_password)
        server.sendmail(from_email, to_email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"Error sending email: {e}")

import requests  # Ensure you have the requests library installed

def get_live_nhl_scores():
    try:
        url = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard"
        response = requests.get(url)
        response.raise_for_status()  # Check for HTTP errors
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
        print(f"Network error occurred: {e}")
        return "Unable to retrieve live NHL scores due to a network error."
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return "An unexpected error occurred while fetching live NHL scores."


    except Exception as e:
        print(f"Error fetching live NHL scores: {e}")
        return "An error occurred while fetching live NHL scores."

def generate_and_send_response(email_content, metadata, attachments):
    max_retries = 5
    delay = 1  # Start with 1 second

    # Update the system instruction
    system_instruction = (
        "Your name is FelzyBot, and you are happy to assist everyone. "
        "When provided with live NHL scores, include them in your response if relevant. "
        "When provided with images, analyze them and incorporate their content into your response. "
        "Generate a creative and helpful reply based on the user's message and any provided data."
    )

    for attempt in range(max_retries):
        try:
            # Load images from attachment paths
            images = []
            for filepath in attachments:
                try:
                    image = Image.open(filepath)
                    images.append(image)
                except Exception as e:
                    print(f"Error loading image {filepath}: {e}")

            # Fetch live NHL scores if requested
            live_scores = ""
            if "nhl scores" in email_content.lower() or "nhl score" in email_content.lower():
                live_scores = get_live_nhl_scores()

            # Prepare the assistant's prompt
            ai_prompt = f"{email_content}"
            if live_scores:
                ai_prompt += f"\n\nHere are the current NHL scores:\n{live_scores}"

            # Generate the response using the updated prompt
            response = client.models.generate_content(
                model=model_id,
                contents=[ai_prompt] + images if images else [ai_prompt],
                config=GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.7,
                    response_modalities=["TEXT"],
                ),
            )

            # Extract the response text
            response_text = ' '.join(
                part.text for part in response.candidates[0].content.parts if part.text
            )
            response_text = response_text.replace('\n', ' ').strip()

            # Print the subject, content, and FelzyBot's response
            print(f"Subject: {metadata['subject']}")
            print(f"Content: {email_content}")
            print(f"FelzyBot's Response: {response_text}\n")

            # Send the response email
            send_email(
                "Response from FelzyBot",
                response_text,
                metadata["from"],
                metadata.get("in_reply_to", "")
            )
            return  # Exit the function if successful

        except Exception as e:
            print(f"Error generating or sending response: {e}")
            if "503" in str(e):
                print("Service unavailable. Retrying...")
                time.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                break  # Exit the loop if the error is not recoverable

def main():
    try:
        # Clear the screen only when the script starts
        os.system('cls' if os.name == 'nt' else 'clear')

        mail = login_gmail()
        if not mail:
            print("Unable to login to Gmail. Exiting.")
            return

        login_time = time.time()

        while True:
            emails_content, email_metadata, email_attachments = read_gmail(mail)
            if emails_content and email_metadata:
                for email_content, metadata, attachments in zip(emails_content, email_metadata, email_attachments):
                    generate_and_send_response(email_content, metadata, attachments)
            else:
                # Only print this message if it's not the first iteration
                print("No new messages at this time.\n")

            # Re-login every 10 minutes
            if time.time() - login_time >= 600:
                mail.logout()
                mail = login_gmail()
                login_time = time.time()
                if not mail:
                    print("Unable to maintain connection to Gmail. Exiting.")
                    break

            time.sleep(10)  # Wait before checking again
    except KeyboardInterrupt:
        print("FelzyBot has been stopped manually.")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()
