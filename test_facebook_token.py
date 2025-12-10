#!/usr/bin/env python3
"""
Test if your Facebook token works
"""

import requests
import os
from dotenv import load_dotenv

load_dotenv()

def test_facebook_token():
    token = os.getenv('FACEBOOK_ACCESS_TOKEN')
    
    if not token:
        print("❌ No FACEBOOK_ACCESS_TOKEN found in .env")
        return
    
    # Test basic API access
    url = f"https://graph.facebook.com/v18.0/me"
    params = {'access_token': token}
    
    response = requests.get(url, params=params)
    data = response.json()
    
    if 'id' in data:
        print(f"✅ Token is VALID!")
        print(f"👤 User ID: {data['id']}")
        print(f"📛 Name: {data.get('name', 'N/A')}")
        
        # Test ad account access
        ad_account_id = os.getenv('FACEBOOK_AD_ACCOUNT_ID')
        if ad_account_id:
            test_ad_account(token, ad_account_id)
        else:
            print("ℹ️  No ad account ID set - skipping ad account test")
            
    else:
        print(f"❌ Token is INVALID: {data}")

def test_ad_account(token, ad_account_id):
    """Test if we can access the ad account"""
    url = f"https://graph.facebook.com/v18.0/{ad_account_id}"
    params = {
        'access_token': token,
        'fields': 'id,name,account_status'
    }
    
    response = requests.get(url, params=params)
    data = response.json()
    
    if 'id' in data:
        print(f"✅ Ad Account Access: SUCCESS")
        print(f"   Account: {data.get('name', 'N/A')}")
        print(f"   Status: {data.get('account_status', 'N/A')}")
    else:
        print(f"❌ Ad Account Access Failed: {data}")

if __name__ == "__main__":
    test_facebook_token()