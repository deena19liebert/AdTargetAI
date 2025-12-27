# app/schemas/campaign.py
"""
Schemas for campaign creation and management
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class CampaignCreateRequest(BaseModel):
    """Request model for creating a new campaign"""
    
    # Basic Info
    product_name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    
    # Platforms
    platforms: List[str] = Field(
        ..., 
        min_items=1,
        description="List of platforms: facebook, instagram, google, youtube, linkedin, twitter, tiktok, snapchat"
    )
    
    # Targeting (LLM will help infer, but user can override)
    target_age_min: Optional[int] = Field(None, ge=13, le=65)
    target_age_max: Optional[int] = Field(None, ge=13, le=65)
    target_gender: Optional[str] = Field(None, description="male, female, all")
    target_locations: Optional[List[str]] = Field(None, description="List of locations")
    target_interests: Optional[List[str]] = Field(None, description="List of interests")
    
    # Budget
    daily_budget_cents: int = Field(..., gt=0, description="Daily budget in paise")
    total_budget_cents: int = Field(..., gt=0, description="Total budget in paise")
    duration_days: int = Field(..., gt=0, le=90, description="Campaign duration")
    
    # Creative
    cta_text: Optional[str] = Field(None, max_length=100)
    ad_copy: Optional[str] = Field(None, max_length=500)
    image_url: Optional[str] = Field(None, description="URL to ad creative")
    
    # Advanced
    use_advanced_targeting: bool = Field(False, description="Use AI-powered targeting")
    objective: Optional[str] = Field(
        None, 
        description="AWARENESS, TRAFFIC, ENGAGEMENT, LEADS, SALES"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "product_name": "EcoFriendly Water Bottle",
                "description": "Sustainable, BPA-free water bottle",
                "platforms": ["facebook", "instagram"],
                "target_age_min": 18,
                "target_age_max": 35,
                "target_gender": "all",
                "target_locations": ["India", "USA"],
                "target_interests": ["fitness", "sustainability", "health"],
                "daily_budget_cents": 50000,  # ₹500
                "total_budget_cents": 1500000,  # ₹15,000
                "duration_days": 30,
                "cta_text": "Shop Now",
                "use_advanced_targeting": False,
                "objective": "SALES"
            }
        }

class CreditCheckResponse(BaseModel):
    """Response for credit balance check before campaign creation"""
    
    has_enough_credits: bool
    current_balance: int
    required_credits: int
    balance_after: int
    is_low_balance: bool
    message: str
    recommended_topup: Optional[Dict[str, Any]] = None

class CampaignCreateResponse(BaseModel):
    """Response after campaign creation"""
    
    success: bool
    message: str
    campaign_id: Optional[str] = None
    
    # Credit info
    credits_deducted: int
    credits_remaining: int
    
    # Campaign details
    platforms_deployed: List[str]
    estimated_reach: Optional[int] = None
    
    # API responses (optional)
    platform_responses: Optional[Dict[str, Any]] = None
    
    # Warnings
    warnings: Optional[List[str]] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)

class CampaignStatusResponse(BaseModel):
    """Response for campaign status check"""
    
    campaign_id: str
    status: str  # pending, active, paused, completed, failed
    platforms: List[str]
    
    # Performance metrics (if available)
    impressions: Optional[int] = None
    clicks: Optional[int] = None
    conversions: Optional[int] = None
    spend_cents: Optional[int] = None
    
    created_at: datetime
    updated_at: Optional[datetime] = None

class CampaignListResponse(BaseModel):
    """Response for listing user campaigns"""
    
    campaigns: List[Dict[str, Any]]
    total_count: int
    total_credits_used: int
    page: int
    page_size: int