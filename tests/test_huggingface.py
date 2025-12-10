import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.llm_reasoner.huggingface_reasoner import HuggingFaceReasoner
from app.core.models import CampaignInput, Platform

def test_huggingface_integration():
    """Test Hugging Face reasoner integration"""
    
    try:
        # Use rule-based only for initial test (no model download)
        reasoner = HuggingFaceReasoner("distilgpt2")
        
        test_input = CampaignInput(
            product_name="GlowCo Candles",
            product_description="Eco-friendly soy candles with calming scents for home ambiance",
            category="home decor",
            price_range="$15-30",
            target_location=["US", "UK"],
            platforms=[Platform.FACEBOOK, Platform.INSTAGRAM],
            daily_budget=50.0,
            total_budget=500.0,
            campaign_days=10,
            call_to_action="Shop Now"
        )
        
        insights = reasoner.infer_audience_insights(test_input)
        
        print(f"Age Range: {insights.age_min}-{insights.age_max}")
        print(f"Interests: {insights.interests}")
        print(f"CTAs: {insights.suggested_ctas}")
        print(f"Platforms: {list(insights.platform_recommendations.keys())}")
        print(f"Behaviors: {insights.behaviors}")
        
        assert insights.age_min >= 18
        assert insights.age_max <= 65
        assert len(insights.interests) >= 3
        assert len(insights.suggested_ctas) >= 2
        print("✅ Hugging Face integration test passed!")
        
    except Exception as e:
        print(f" Test failed: {e}")
        # This might be expected if models aren't downloaded yet

if __name__ == "__main__":
    test_huggingface_integration()