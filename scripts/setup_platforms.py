#!/usr/bin/env python3
"""
Quick setup script for all advertising platforms
"""

def print_setup_instructions():
    print("🚀 AdTargetAI - Multi-Platform Setup Guide")
    print("=" * 50)
    
    platforms = {
        'facebook': 'https://developers.facebook.com/docs/marketing-api',
        'google_ads': 'https://developers.google.com/google-ads/api/docs/start',
        'tiktok': 'https://ads.tiktok.com/marketing_api',
        'linkedin': 'https://docs.microsoft.com/en-us/linkedin/marketing/',
        'pinterest': 'https://developers.pinterest.com/docs/redoc/',
        'twitter': 'https://developer.twitter.com/en/docs/ads'
    }
    
    for platform, url in platforms.items():
        print(f"\n📱 {platform.upper()}")
        print(f"   Documentation: {url}")
        print(f"   Environment variables needed:")
        
        if platform == 'facebook':
            print("   - FACEBOOK_ACCESS_TOKEN")
            print("   - FACEBOOK_APP_SECRET")
            print("   - FACEBOOK_APP_ID") 
            print("   - FACEBOOK_AD_ACCOUNT_ID")
        elif platform == 'google_ads':
            print("   - GOOGLE_ADS_DEVELOPER_TOKEN")
            print("   - GOOGLE_ADS_REFRESH_TOKEN")
            print("   - GOOGLE_ADS_CLIENT_ID")
            print("   - GOOGLE_ADS_CLIENT_SECRET")
            print("   - GOOGLE_ADS_CUSTOMER_ID")
        # ... add other platforms
    
    print(f"\n💡 Tip: Start with one platform (Facebook recommended) and add others gradually")

if __name__ == "__main__":
    print_setup_instructions()