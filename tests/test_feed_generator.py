import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.feed_generator.platform_generator import PlatformDataGenerator
from app.core.models import CampaignInput, AudienceInsights, Platform
import json

def test_facebook_feed_generation():
    """Test Facebook ad feed generation"""
    generator = PlatformDataGenerator()
    
    campaign_input = CampaignInput(
        product_name="GlowCo Candles",
        product_description="Eco-friendly soy candles with calming scents",
        category="home decor",
        price_range="$15-30",
        target_location=["US", "UK"],
        platforms=[Platform.FACEBOOK, Platform.INSTAGRAM],
        daily_budget=50.0,
        total_budget=500.0,
        campaign_days=10,
        call_to_action="Shop Now"
    )
    
    audience_insights = AudienceInsights(
        age_min=25,
        age_max=45,
        genders=["female", "male"],
        interests=["home decor", "sustainability", "wellness", "self care"],
        behaviors=["online shopping", "social media"],
        locations=["US", "UK"],
        languages=["English"],
        suggested_ctas=["Shop Now", "Discover Scents", "Create Ambiance"],
        campaign_objectives=["conversions"],
        platform_recommendations={}
    )
    
    feeds = generator.generate_platform_feeds(campaign_input, audience_insights)
    
    assert "facebook" in feeds
    assert "targeting_spec" in feeds["facebook"]
    assert "ad_creative" in feeds["facebook"]
    
    print("✅ Facebook feed generation test passed!")
    print(f"Generated Facebook spec: {json.dumps(feeds['facebook'], indent=2)}")

def test_multiple_platforms():
    """Test generation for multiple platforms"""
    generator = PlatformDataGenerator()
    
    campaign_input = CampaignInput(
        product_name="Test Product",
        product_description="Test description",
        category="technology",
        price_range="$100-200",
        target_location=["US"],
        platforms=[Platform.FACEBOOK, Platform.TIKTOK, Platform.GOOGLE],
        daily_budget=100.0,
        total_budget=1000.0,
        campaign_days=10,
        call_to_action="Buy Now"
    )
    
    audience_insights = AudienceInsights(
        age_min=18,
        age_max=35,
        genders=["male", "female"],
        interests=["technology", "gadgets", "innovation"],
        behaviors=["early adopters"],
        locations=["US"],
        languages=["English"],
        suggested_ctas=["Buy Now", "Learn More"],
        campaign_objectives=["conversions"],
        platform_recommendations={}
    )
    
    feeds = generator.generate_platform_feeds(campaign_input, audience_insights)
    
    assert len(feeds) == 3
    assert all(platform in feeds for platform in ["facebook", "tiktok", "google"])
    
    print("✅ Multiple platforms test passed!")
    print(f"Generated platforms: {list(feeds.keys())}")

if __name__ == "__main__":
    test_facebook_feed_generation()
    test_multiple_platforms()
    print("🎉 All feed generator tests passed!")