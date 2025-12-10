import os
from typing import Optional

class FacebookConfig:
    """Facebook API configuration"""
    
    @staticmethod
    def validate_config() -> bool:
        """Check if Facebook config is present"""
        required_vars = [
            'FACEBOOK_ACCESS_TOKEN',
            'FACEBOOK_APP_SECRET', 
            'FACEBOOK_APP_ID',
            'FACEBOOK_AD_ACCOUNT_ID'
        ]
        
        missing = [var for var in required_vars if not os.getenv(var)]
        if missing:
            print(f"⚠️  Missing Facebook config: {', '.join(missing)}")
            print("   Get these from: https://developers.facebook.com/")
            return False
        return True
    
    @staticmethod
    def get_required_scopes() -> list:
        """Get required Facebook permissions"""
        return [
            'ads_management',
            'business_management', 
            'ads_read',
            'public_profile'
        ]
    
    @staticmethod
    def get_ad_account_prefix() -> str:
        """Facebook ad account ID prefix"""
        return "act_"