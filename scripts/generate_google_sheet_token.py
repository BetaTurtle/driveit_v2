"""
Script to generate a Google Sheets OAuth token.

Usage:
1. Ensure `client_secret.json` is in the project root. This file comes from the Google Cloud Console (OAuth 2.0 Client IDs > Desktop App).
2. Run this script: `python scripts/generate_google_sheet_token.py`
3. Follow the browser prompts to authenticate.
4. The script will print the strict JSON token string. Copy this into your `.env` file as `GOOGLE_SHEETS_TOKEN`.

Dependencies:
- google-auth-oauthlib
- google-auth
- google-api-python-client
"""

import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

# Scope for reading and writing to Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def main():
    print("Looking for client_secret.json...")
    if not os.path.exists('client_secret.json'):
        print("Error: client_secret.json not found. Please download it from Google Cloud Console (OAuth Desktop App) and place it in this directory.")
        return

    print("Starting OAuth flow. A browser window should open...")
    flow = InstalledAppFlow.from_client_secrets_file(
        'client_secret.json', SCOPES)
    
    # Run the local server flow
    creds = flow.run_local_server(port=0)
    
    # Convert to JSON
    token_json = creds.to_json()
    
    # Save to file
    with open('token.json', 'w') as token_file:
        token_file.write(token_json)
    
    print("\nSUCCESS! Token generated and saved to 'token.json'.")
    print("Here is your token string for the .env file (GOOGLE_SHEETS_TOKEN):")
    print("-" * 20)
    print(token_json)
    print("-" * 20)
    print("Copy the content between the dashes and paste it into `.env` or your secret manager.")

if __name__ == '__main__':
    main()
