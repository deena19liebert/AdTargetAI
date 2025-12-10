# app/export_manager/base_exporter.py
from abc import ABC, abstractmethod
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class BaseExporter(ABC):
    """Base class for all platform exporters"""
    
    @abstractmethod
    async def create_campaign(self, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create campaign on the platform - must be implemented by subclasses"""
        pass
    
    @abstractmethod
    def export_campaign(self, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format campaign data for platform API - must be implemented by subclasses"""
        pass
    
    def _extract_common_data(self, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract common campaign data used by all platforms"""
        campaign_input = campaign_data.get('campaign_input', {})
        audience_insights = campaign_data.get('audience_insights', {})
        
        return {
            'product_name': campaign_input.get('product_name', 'Unknown Product'),
            'product_description': campaign_input.get('product_description', ''),
            'category': campaign_input.get('category', ''),
            'price_range': campaign_input.get('price_range', ''),
            'daily_budget': campaign_input.get('daily_budget', 50),
            'total_budget': campaign_input.get('total_budget', 500),
            'campaign_days': campaign_input.get('campaign_days', 7),
            'call_to_action': campaign_input.get('call_to_action', 'Learn More'),
            'audience_insights': audience_insights,
            'campaign_strategy': campaign_data.get('campaign_strategy', {})
        }