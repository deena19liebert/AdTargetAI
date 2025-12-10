# app/export_manager/tiktok_exporter.py
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List
from app.export_manager.base_exporter import BaseExporter

logger = logging.getLogger(__name__)

class TikTokExporter(BaseExporter):
    """TikTok exporter without external SDK dependency"""
    
    async def create_campaign(self, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create TikTok campaign - mock implementation"""
        await asyncio.sleep(1)  # Simulate API call
        
        return {
            "status": "success",
            "platform": "tiktok",
            "campaign_id": f"mock_tiktok_{int(datetime.now().timestamp())}",
            "ad_group_id": f"mock_adgroup_{int(datetime.now().timestamp())}",
            "ad_id": f"mock_ad_{int(datetime.now().timestamp())}",
            "message": "TikTok campaign created (mock - add TikTok Business API credentials for real creation)"
        }
    
    def export_campaign(self, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format campaign data for TikTok API"""
        common_data = self._extract_common_data(campaign_data)
        audience = common_data['audience_insights']
        
        return {
            "platform": "tiktok",
            "campaign_spec": {
                "name": f"TikTok - {common_data['product_name']}",
                "objective": self._map_objective(audience.get('campaign_objectives', [])),
                "budget_mode": "DAY",
                "budget": common_data['daily_budget']
            },
            "targeting": self._build_tiktok_targeting(audience),
            "creative": {
                "ad_name": f"Ad - {common_data['product_name']}",
                "creative_type": "VIDEO",
                "call_to_action": self._map_cta(audience.get('suggested_ctas', ['Learn More'])[0]),
                "ad_text": common_data['product_description'][:100]
            }
        }
    
    def _build_tiktok_targeting(self, audience_insights: Dict[str, Any]) -> Dict[str, Any]:
        """Build TikTok targeting spec"""
        return {
            "age_range": [audience_insights.get('age_min', 18), audience_insights.get('age_max', 35)],
            "gender": [g.upper() for g in audience_insights.get('genders', ['male', 'female'])],
            "location": [{"country_code": loc} for loc in audience_insights.get('locations', ['US'])],
            "interests": audience_insights.get('interests', [])[:5],
            "audience_type": "CUSTOM"
        }
    
    def _map_objective(self, objectives: List[str]) -> str:
        """Map objectives to TikTok objectives"""
        objective_map = {
            'conversions': 'CONVERSIONS',
            'awareness': 'REACH',
            'engagement': 'ENGAGEMENT',
            'traffic': 'TRAFFIC'
        }
        
        for objective in objectives:
            if objective.lower() in objective_map:
                return objective_map[objective.lower()]
        
        return 'CONVERSIONS'
    
    def _map_cta(self, cta: str) -> str:
        """Map CTA to TikTok CTA types"""
        cta_map = {
            'shop now': 'SHOP_NOW',
            'learn more': 'LEARN_MORE',
            'sign up': 'SIGN_UP',
            'download': 'DOWNLOAD'
        }
        return cta_map.get(cta.lower(), 'LEARN_MORE')