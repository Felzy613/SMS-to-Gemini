
# SMS to Google Gemini

A Python-powered SMS chatbot that connects your Google Voice number to Google's Generative AI. When a text is sent to your Google Voice number, it’s forwarded via Gmail, processed by the AI, and the response is sent back as a text message. Enjoy automated, interactive conversations on your mobile device!

---

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
  - [Downloading the Script](#downloading-the-script)
  - [Creating a Virtual Environment (optional)](#creating-a-virtual-environment-optional)
  - [Installing Dependencies](#installing-dependencies)
  - [Environment Variables](#environment-variables)
- [Configuration](#configuration)
  - [Obtaining Google GenAI API Key](#obtaining-google-genai-api-key)
  - [Setting Up Gmail API](#setting-up-gmail-api)
  - [Configuring Google Voice Number](#configuring-google-voice-number)
- [Running the Script](#running-the-script)
- [Communicating with FelzyBot](#communicating-with-felzybot)
- [Troubleshooting & FAQs](#troubleshooting--faqs)
- [Contribution Guidelines](#contribution-guidelines)
- [License](#license)
- [Disclaimer](#disclaimer)

---

## Overview

SMS to Google Gemini is designed to create a seamless relay between your Google Voice texts and Google's Generative AI. It's perfect for automating SMS responses with an intelligent twist—build your own interactive chatbot with just a few configurations while maintaining privacy and control over your messages.

---

## Prerequisites

Before you begin, ensure you have the following:

- **Python 3** (download [here](https://www.python.org/downloads/))
- A **Google Cloud Account** with access to the Generative AI API and Gmail API.
- A **Gmail Account** (consider creating a dedicated account for this project).
- A **Google Voice Number** with texts forwarded to Gmail.
- An **API Key** for Google's Generative AI.
- **Google OAuth2** setup for Gmail API access.

---

## Setup

### Downloading the Script

Save the `SMS to Gemini.py` file onto your local machine.

### Creating a Virtual Environment (optional)

To keep your dependencies isolated, create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

If you choose this route, install the \`python-dotenv\` library to handle your environment variables:

```bash
pip install python-dotenv
```

### Installing Dependencies

Install all required Python packages by running:

```bash
pip install -r requirements.txt
```

### Key Packages

The following Python packages are integral to the functionality of the script:

- **google-genai**: Interact with Google’s Generative AI API, enabling AI-driven operations.
- **requests**: A widely used library for making HTTP requests in Python.
- **google-auth-oauthlib**: Handles the OAuth 2.0 authorization flow for interacting with Google's APIs.
- **google-api-python-client**: Provides a Python interface to various Google APIs, including the Gmail API.
- **pillow**: A Python library for image processing tasks such as opening, manipulating, and saving images.
- **python-dotenv**: Simplifies the management of environment variables during development by reading them from a `.env` file.
  
### Environment Variables

Add the following settings to your system environment variables or create a \`.env\` file in your project directory:

```dotenv
API_KEY=your_google_genai_api_key
```

This simplifies configuration and helps keep sensitive keys secure.

---

## Configuration

### Obtaining Google GenAI API Key

1. **Access Google Cloud Console:**
   - Go to the [Google Cloud Console](https://console.cloud.google.com/).

2. **Create or Select a Project:**
   - Create a new project or select an existing one.

3. **Enable Generative AI APIs:**
   - Navigate to **APIs & Services ➔ Library**, then search for "Generative AI" and enable the API.

4. **Create Credentials:**
   - Go to **APIs & Services ➔ Credentials**, click **Create Credentials ➔ API Key**, and copy the generated API key.

5. **Add API Key:**
   - Use this key as your \`API_KEY\` in the environment variable settings.

### Setting Up Gmail API

To allow your script to check and send emails using Gmail, follow these steps:

1. **Visit Google Developers Console:**
   - Go to the [Google Cloud Console](https://console.cloud.google.com/).

2. **Create or Select a Project:**
   - Use your existing project for the Google GenAI API or create a new one.

3. **Enable the Gmail API:**
   - Click on **Enable APIs and Services**.
   - In the API Library, search for **Gmail API** and select it.
   - Click **Enable**.

4. **Configure OAuth Consent Screen:**
   - Navigate to **APIs & Services ➔ OAuth consent screen**.
   - Choose **External** if your application is for testing or public use, then click **Create**.
   - Fill in the required fields like **Application Name**, **Support Email**, etc.
   - Save and continue through the scopes page (you can add minimal scopes for just sending and reading Gmail messages).

5. **Create OAuth 2.0 Credentials:**
   - Go to **APIs & Services ➔ Credentials**.
   - Click **Create Credentials ➔ OAuth client ID**.
   - Choose **Desktop App** and give it an appropriate name.
   - Click **Create**.
   - Download the JSON file containing your OAuth credentials (commonly named \`credentials.json\`), and place it in your project root.


### Configuring Google Voice Number

1. **Sign in to Google Voice:**
   - Log in at [Google Voice](https://voice.google.com/) using the same Gmail account configured above.

2. **Set Up a New Google Voice Number:**
   - Follow the on-screen prompts to obtain a new number.

3. **Enable Text Forwarding:**
   - Click the **Settings** icon (gear icon) at the top right.
   - Navigate to the **Messages** tab.
   - Enable **Forward messages to email** and verify that your Gmail address is correct.

---

## Running the Script

Start the script by running:

```bash
python "SMS to Gemini.py"
```

The script will perform the following tasks:
- Log in to your Gmail account via OAuth2.
- Continuously check for new messages sent to your Google Voice number.
- Process incoming texts and generate responses using Google's Generative AI.
- Send replies back via email to your Google Voice number, which will then forward them as texts.

Press \`Ctrl+C\` to stop the script.

---

## Communicating with FelzyBot

To interact with the chatbot:

- **Send a text message** to your configured Google Voice number.
- **FelzyBot** will receive the forwarded email.
- The **Generative AI processes your message** and crafts a response.
- The **reply is emailed back** to your Google Voice, which pushes it to your phone as a text message.

---

## Troubleshooting & FAQs

### Common Issues

- **Gmail API Authorization**:  
  If you encounter issues during OAuth2 authorization, verify that your \`credentials.json\` file is in the correct location and that your OAuth consent screen is properly configured.
  
- **API Key Errors**:  
  Ensure that your \`API_KEY\` environment variable matches the key generated from your Google Cloud Console.
  
- **Dependency Issues**:  
  Check that all dependencies are installed by re-running \`pip install -r requirements.txt\`. If you experience version conflicts, consider using a virtual environment.

### FAQs

**Q: How do I check if the script is receiving texts?**  
A: Look for log messages indicating new emails being processed. Use print statements or logging for debugging.

**Q: Can I integrate image processing with this tool?**  
A: Yes, while the current version supports sending images, image generation isn’t supported yet. Suggestions for image generation integrations are welcome.

---

## Contribution Guidelines

Contributions are welcome! If you encounter issues, have suggestions, or want to improve the code:

- **Fork the repository.**
- **Create a new branch** for your feature or bug fix.
- **Submit a Pull Request** with a detailed description of your changes.
- **Open an Issue** if you have any questions or improvements to discuss.

For more details, refer to the \`CONTRIBUTING.md\` file included in the repository (if available).

---

## License

Distributed under the MIT License. See the \`LICENSE\` file for more details.

---

## Disclaimer

**BEWARE:** Google may ban your Google Voice account if they find out you are using it for automated chatbot interactions. Use this tool responsibly and at your own risk.
