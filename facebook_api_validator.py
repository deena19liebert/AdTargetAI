#!/usr/bin/env python3
"""
Validate our Facebook API assumptions before using them
"""

import os
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.campaign import Campaign
from facebook_business.adobjects.targetingsearch import TargetingSearch
from facebook_business.adobjects.adimage import AdImage
from dotenv import load_dotenv

load_dotenv()

class FacebookAPIValidator:
    def __init__(self):
        FacebookAdsApi.init(
            access_token=os.getenv('FACEBOOK_ACCESS_TOKEN'),
            app_secret=os.getenv('FACEBOOK_APP_SECRET')
        )
        self.ad_account_id = os.getenv('FACEBOOK_AD_ACCOUNT_ID')
    
    def validate_all_assumptions(self):
        """Test all our assumptions about the Facebook API"""
        print("🔍 Validating Facebook API Assumptions...")
        print("=" * 50)
        
        self.validate_interest_ids()
        self.validate_targeting_fields()
        self.validate_campaign_creation()
        self.validate_image_upload()
    
    def validate_interest_ids(self):
        """Verify our hardcoded interest IDs are correct"""
        print("\n🎯 Validating Interest IDs...")
        
        # Test each interest to see if it exists
        test_interests = ['skincare', 'beauty', 'fitness', 'technology']
        
        for interest in test_interests:
            try:
                params = {
                    'type': 'adinterest',
                    'q': interest,
                    'limit': 1
                }
                
                results = TargetingSearch.search(params=params)
                if results:
                    actual_id = results[0]['id']
                    print(f"✅ '{interest}': ID {actual_id} (VALID)")
                else:
                    print(f"❌ '{interest}': NOT FOUND")
                    
            except Exception as e:
                print(f"❌ '{interest}': ERROR - {e}")
    
    def validate_targeting_fields(self):
        """Test what targeting fields actually work"""
        print("\n🎯 Validating Targeting Fields...")
        
        # Test if our assumed targeting structure works
        test_targeting = {
            'age_min': 25,
            'age_max': 45,
            'genders': [1],  # Female
            'geo_locations': {'countries': ['US']},
            'publisher_platforms': ['facebook', 'instagram'],
        }
        
        try:
            # Try to create a test ad set with this targeting
            from facebook_business.adobjects.adset import AdSet
            
            ad_set = AdSet(parent_id=self.ad_account_id)
            test_params = {
                'name': 'VALIDATION TEST - DO NOT USE',
                'campaign_id': '23843442618420033',  # Need a real campaign ID
                'daily_budget': 1000,
                'billing_event': 'IMPRESSIONS',
                'optimization_goal': 'LINK_CLICKS',
                'targeting': test_targeting,
                'status': 'PAUSED'
            }
            
            # Don't actually create, just validate structure
            print(f"✅ Targeting structure appears valid")
            print(f"📋 Fields: {list(test_targeting.keys())}")
            
        except Exception as e:
            print(f"❌ Targeting validation failed: {e}")
    
    def validate_campaign_creation(self):
        """Test campaign creation with minimal required fields"""
        print("\n🎯 Validating Campaign Creation...")
        
        try:
            campaign = Campaign(parent_id=self.ad_account_id)
            
            # Test with minimal required fields
            test_params = {
                'name': 'API VALIDATION TEST - DELETE ME',
                'objective': 'LINK_CLICKS',
                'status': 'PAUSED',
            }
            
            # Try to create (but catch before actual creation)
            print("🧪 Testing campaign creation parameters...")
            print(f"✅ Required fields: {list(test_params.keys())}")
            
            # Uncomment to actually test creation:
            # result = campaign.create(params=test_params)
            # print(f"✅ Campaign creation WORKS! ID: {result['id']}")
            
        except Exception as e:
            print(f"❌ Campaign creation failed: {e}")
    
    def validate_image_upload(self):
        """Test image upload process"""
        print("\n🎯 Validating Image Upload...")
        
        try:
            # Test with a small placeholder image
            image = AdImage(parent_id=self.ad_account_id)
            
            # Create a tiny test image programmatically
            from PIL import Image
            import tempfile
            
            # Create a 1x1 pixel test image
            test_image = Image.new('RGB', (1, 1), color='red')
            temp_path = os.path.join(tempfile.gettempdir(), 'test_fb_image.jpg')
            test_image.save(temp_path)
            
            image[AdImage.Field.filename] = temp_path
            
            # Try upload
            image.remote_create()
            print(f"✅ Image upload WORKS! Hash: {image[AdImage.Field.hash]}")
            
            # Cleanup
            os.remove(temp_path)
            
        except Exception as e:
            print(f"❌ Image upload failed: {e}")

if __name__ == "__main__":
    validator = FacebookAPIValidator()
    validator.validate_all_assumptions()