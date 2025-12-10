#!/usr/bin/env python3
"""
Extend Facebook Access Token to 60 days
"""

import requests
import os
from dotenv import load_dotenv

load_dotenv()

def extend_facebook_token():
    # Your short-lived token (the one you just copied)
    short_lived_token = input("Paste your short-lived token: ").strip()
    
    # Your app credentials from .env
    app_id = os.getenv('FACEBOOK_APP_ID')
    app_secret = os.getenv('FACEBOOK_APP_SECRET')
    
    if not app_id or not app_secret:
        print("❌ Please set FACEBOOK_APP_ID and FACEBOOK_APP_SECRET in your .env file first")
        return
    
    # Request long-lived token
    url = f"https://graph.facebook.com/v18.0/oauth/access_token"
    params = {
        'grant_type': 'fb_exchange_token',
        'client_id': app_id,
        'client_secret': app_secret,
        'fb_exchange_token': short_lived_token
    }
    
    response = requests.get(url, params=params)
    data = response.json()
    
    if 'access_token' in data:
        long_lived_token = data['access_token']
        print(f"\n🎉 SUCCESS! Your long-lived token (60 days):")
        print(f"🔑 {long_lived_token}")
        print(f"\n📝 Add this to your .env file as:")
        print(f"FACEBOOK_ACCESS_TOKEN={long_lived_token}")
    else:
        print(f"❌ Error: {data}")

if __name__ == "__main__":
    extend_facebook_token()