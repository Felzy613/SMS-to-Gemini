# SMS to Google Gemini.

## Prerequisites

- **Python 3.7+**
- **Google Cloud Account** with Generative AI API access
- **Gmail Account** with IMAP access enabled (suggested to create a new Google account specifically for this project)
- **Google Voice Number** with text forwarding to Gmail
- **API Key** for Google's Generative AI
- **Gmail App Password** (requires 2FA to be enabled)

## Setup

### Download the Script
Save the `SMS to Gemini.py` file to your local machine.

### Create a Virtual Environment (optional)
```bash
python -m venv venv
source venv/bin/activate
```
 On Windows use `venv\Scripts\activate`

 **If you are going to use a Virtual Environment make sure to install the "python-dotenv" library.**
 ```bash
  pip install python-dotenv
```


### Install Dependencies
```bash
pip install -r requirements.txt
```

### Set Up Environment Variables
**Add these settings to your system Environment Variables:**

API_KEY=your_google_genai_api_key

EMAIL_ADDRESS=your_email@gmail.com

EMAIL_PASSWORD=your_Gmail_app_password

## Configuration

### Enable IMAP in Gmail
Go to Gmail Settings ➔ See all settings.

Navigate to the Forwarding and POP/IMAP tab.

In the IMAP access section, select Enable IMAP.

Click Save Changes.

### Generate an App Password (requires 2FA)** 

Go to Google Account Security.

Enable 2-Step Verification if it's not already enabled.

After enabling 2FA, search App Passwords in the search bar of your Google account settings page.

You might need to sign in again.

You can name the app password whatever you like.

Click Generate.

Copy the 16-character password and use it as your "EMAIL_PASSWORD" (DO NOT include the spaces in the passowrd).

### Obtain Google GenAI API Key

Go to Google Cloud Console.

Create a new project or select an existing one.

Enable the Generative AI APIs:

Navigate to APIs & Services ➔ Library.

Search for Generative AI and enable it.

Go to APIs & Services ➔ Credentials.

Click Create Credentials ➔ API Key.

Copy the API key and use it as your "API_KEY"

### Obtain and Configure Google Voice Number

Go to Google Voice and sign in with the same google account as your gmail account.

Follow the prompts to Set up a new number.

**Once you have your Google Voice number, enable text forwarding:**

Click on the Settings icon (gear icon) in the top right corner.

Navigate to the Messages tab.

Enable Forward messages to email.

Ensure your Gmail address is correct.

## Running the Script

Start the script by running:

```bash
python SMS to Gemini.py
```

The script will:

Log in to your Gmail account.

Continuously check for new messages sent to your Google Voice number.

Process incoming texts and generate responses using Google's Generative AI.

Send replies back via email to your Google Voice number, which will forward them as texts.

*To stop the script, press Ctrl+C.*

## Communicating with FelzyBot:
Send a text message to your Google Voice number.

FelzyBot will receive the forwarded email and generate a response.

The response will be sent back to your phone as a text message via Google Voice.

## Dependencies
Ensure you have the following Python packages installed:

google-genai

requests

pillow

python-dotenv

You can install them all with:

```bash
pip install google-genai requests pillow python-dotenv
```

### Note: 
This does support sending images to the chatbot however it does not yet support generating images.
If anyone has any ideas on how to make image generation work with google voice, let me know.
If you encounter any issues or have questions during setup, don't hesitate to reach out for help. Enjoy!


# BEWARE GOOGLE MAY BAN YOUR GOOGLE VOICE ACCOUNT IF THEY FIND OUT YOU ARE USING IT FOR THIS CHATBOT.
