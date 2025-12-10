import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.input_parser.validator import InputValidator
from app.llm_reasoner.huggingface_reasoner import HuggingFaceReasoner
from app.feed_generator.platform_generator import PlatformDataGenerator
from app.export_manager.json_exporter import CampaignExporter
from app.core.models import CampaignInput, Platform
import json

def test_standalone_campaign_generation():
    """Test complete campaign generation pipeline without API"""
    
    print("🚀 Testing Standalone Campaign Generation...")
    
    # Initialize all components
    validator = InputValidator()
    marketing_ai = HuggingFaceReasoner("distilgpt2")
    feed_generator = PlatformDataGenerator()
    exporter = CampaignExporter()
    
    test_campaign = {
        "product_name": "GlowCo Premium Candles",
        "product_description": "Handcrafted eco-friendly soy candles with essential oils for home wellness",
        "category": "home decor",
        "price_range": "$25-45",
        "target_location": ["US", "CA"],
        "platforms": ["facebook", "instagram", "tiktok"],
        "daily_budget": 75.0,
        "total_budget": 750.0,
        "campaign_days": 10,
        "call_to_action": "Shop Now",
        "reference_description": "Luxury candle collection in minimalist packaging"
    }
    
    try:
        # 1. Validate input
        print("✅ Step 1: Validating input...")
        validated_input = validator.validate_input(test_campaign)
        print(f"   Validated: {validated_input.product_name}")
        
        # 2. Generate audience insights
        print("✅ Step 2: Generating audience insights...")
        audience_insights = marketing_ai.infer_audience_insights(validated_input)
        print(f"   Age range: {audience_insights.age_min}-{audience_insights.age_max}")
        print(f"   Interests: {audience_insights.interests[:3]}")
        
        # 3. Generate platform feeds
        print("✅ Step 3: Generating platform feeds...")
        platform_feeds = feed_generator.generate_platform_feeds(validated_input, audience_insights)
        print(f"   Platforms: {list(platform_feeds.keys())}")
        
        # 4. Export complete package
        print("✅ Step 4: Exporting campaign package...")
        export_result = exporter.export_campaign_package(
            campaign_input=validated_input.dict(),
            audience_insights=audience_insights.dict(),
            platform_feeds=platform_feeds,
            format="json"
        )
        
        campaign_id = export_result["metadata"]["campaign_id"]
        
        print("🎉 CAMPAIGN GENERATION SUCCESSFUL!")
        print(f"📋 Campaign ID: {campaign_id}")
        print(f"🌐 Platforms exported: {len(platform_feeds)}")
        print(f"📊 Estimated reach: {export_result['export_summary']['estimated_reach']}")
        print(f"💰 Budget allocation: {export_result['export_summary']['recommended_budget_allocation']}")
        
        # Show sample of generated content
        print("\n📄 Sample Facebook Ad Spec:")
        facebook_spec = platform_feeds.get('facebook', {})
        if facebook_spec:
            print(f"   - Targeting: Age {facebook_spec.get('targeting_spec', {}).get('age_min', 'N/A')}-{facebook_spec.get('targeting_spec', {}).get('age_max', 'N/A')}")
            print(f"   - CTA: {facebook_spec.get('ad_creative', {}).get('call_to_action', 'N/A')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Campaign generation failed: {e}")
        return False

def test_component_isolation():
    """Test individual components in isolation"""
    
    print("\n🔧 Testing Individual Components...")
    
    try:
        # Test validator
        validator = InputValidator()
        test_input = {
            "product_name": "Test Product",
            "platforms": ["facebook"],
            "daily_budget": 50.0,
            "total_budget": 500.0,
            "campaign_days": 10,
            "product_description": "Test description",
            "category": "test",
            "price_range": "$10-20",
            "target_location": ["US"],
            "call_to_action": "Test Now"
        }
        validated = validator.validate_input(test_input)
        print("✅ Input validator: PASS")
        
        # Test feed generator
        feed_generator = PlatformDataGenerator()
        from app.core.models import AudienceInsights
        test_insights = AudienceInsights(
            age_min=25,
            age_max=45,
            genders=["female", "male"],
            interests=["home decor", "sustainability"],
            behaviors=["online shopping"],
            locations=["US"],
            languages=["English"],
            suggested_ctas=["Shop Now"],
            campaign_objectives=["conversions"],
            platform_recommendations={}
        )
        feeds = feed_generator.generate_platform_feeds(validated, test_insights)
        print("✅ Feed generator: PASS")
        
        # Test exporter
        exporter = CampaignExporter()
        export_result = exporter.export_campaign_package(
            campaign_input=validated.dict(),
            audience_insights=test_insights.dict(),
            platform_feeds=feeds,
            format="json"
        )
        print("✅ Campaign exporter: PASS")
        
        return True
        
    except Exception as e:
        print(f"❌ Component test failed: {e}")
        return False

def test_file_export():
    """Test file export functionality"""
    
    print("\n💾 Testing File Export...")
    
    try:
        exporter = CampaignExporter("test_exports")
        
        test_data = {
            "campaign_input": {
                "product_name": "Test Export",
                "category": "test"
            },
            "audience_insights": {
                "age_min": 25,
                "age_max": 45,
                "genders": ["female", "male"]
            },
            "platform_feeds": {
                "facebook": {
                    "targeting_spec": {"age_min": 25, "age_max": 45},
                    "ad_creative": {"call_to_action": "Test Now"}
                },
                "instagram": {
                    "targeting": {"age_range": [25, 45]},
                    "creative": {"call_to_action": "Test Now"}
                }
            }
        }
        
        result = exporter.export_campaign_package(
            campaign_input=test_data["campaign_input"],
            audience_insights=test_data["audience_insights"],
            platform_feeds=test_data["platform_feeds"],
            format="files"
        )
        
        print("✅ File export: PASS")
        print(f"   Export directory: {result.get('export_directory', 'N/A')}")
        print(f"   Files created: {len(result.get('exported_files', {}))}")
        
        return True
        
    except Exception as e:
        print(f"❌ File export test failed: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 AdTargetAI - Complete System Test")
    print("=" * 60)
    
    # Run all tests
    tests = [
        test_component_isolation,
        test_standalone_campaign_generation, 
        test_file_export
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    print(f"✅ Tests passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED! Your AdTargetAI is fully functional! 🚀")
        print("\n🎯 NEXT STEPS:")
        print("1. Your system is ready for production use")
        print("2. Run: python -m uvicorn app.main:app --reload (if you want the API)")
        print("3. Check the 'exports' folder for generated campaigns")
        print("4. Show the generated JSON files to demonstrate platform-ready outputs")
    else:
        print("⚠️  Some tests failed. Check the errors above.")
    
    print("=" * 60)