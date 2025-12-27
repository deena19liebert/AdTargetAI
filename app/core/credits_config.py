# app/core/credits_config.py
"""
Credit system configuration for campaign creation
"""

from enum import Enum
from typing import Dict

class CreditCostType(str, Enum):
    """Different cost types based on campaign complexity"""
    BASIC = "basic"           # Single platform, basic targeting
    STANDARD = "standard"     # Multiple platforms, standard targeting
    ADVANCED = "advanced"     # Multiple platforms, advanced targeting, A/B testing
    PREMIUM = "premium"       # Enterprise features, custom audiences

# Base credit costs for campaigns
CAMPAIGN_CREDIT_COSTS: Dict[CreditCostType, int] = {
    CreditCostType.BASIC: 10,      # Single platform (Facebook OR Instagram)
    CreditCostType.STANDARD: 15,   # 2-3 platforms
    CreditCostType.ADVANCED: 25,   # 4+ platforms with advanced targeting
    CreditCostType.PREMIUM: 50,    # All platforms + custom features
}

# Platform-specific costs (if you want granular pricing)
PLATFORM_COSTS = {
    "facebook": 5,
    "instagram": 5,
    "google": 8,
    "youtube": 8,
    "linkedin": 10,
    "twitter": 6,
    "tiktok": 7,
    "snapchat": 6,
}

def calculate_campaign_cost(platforms: list, has_advanced_targeting: bool = False) -> int:
    """
    Calculate credit cost based on campaign parameters
    
    Args:
        platforms: List of platform names
        has_advanced_targeting: Whether advanced targeting is used
        
    Returns:
        Total credits required
    """
    num_platforms = len(platforms)
    
    # Base cost calculation
    if num_platforms == 1:
        cost = CAMPAIGN_CREDIT_COSTS[CreditCostType.BASIC]
    elif num_platforms <= 3:
        cost = CAMPAIGN_CREDIT_COSTS[CreditCostType.STANDARD]
    else:
        cost = CAMPAIGN_CREDIT_COSTS[CreditCostType.ADVANCED]
    
    # Add premium for advanced targeting
    if has_advanced_targeting:
        cost += 5
    
    return cost

def get_subscription_credit_bonus(tier: str) -> int:
    """
    Get bonus credits when user subscribes
    
    Args:
        tier: Subscription tier (starter, professional, enterprise)
        
    Returns:
        Number of bonus credits
    """
    bonuses = {
        "free": 0,
        "starter": 50,        # ₹29/mo → 50 credits bonus
        "professional": 200,  # ₹99/mo → 200 credits bonus
        "enterprise": 500,    # ₹299/mo → 500 credits bonus
    }
    return bonuses.get(tier.lower(), 0)

def get_subscription_discount(tier: str) -> float:
    """
    Get credit purchase discount percentage based on subscription tier
    
    Args:
        tier: Subscription tier
        
    Returns:
        Discount as decimal (0.10 = 10% off)
    """
    discounts = {
        "free": 0.0,
        "starter": 0.10,      # 10% off credit purchases
        "professional": 0.20, # 20% off credit purchases
        "enterprise": 0.30,   # 30% off credit purchases
    }
    return discounts.get(tier.lower(), 0.0)

# Minimum credits required to create a campaign
MIN_CREDITS_REQUIRED = 10

# Low balance warning threshold
LOW_BALANCE_THRESHOLD = 20