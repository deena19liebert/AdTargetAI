# app/schemas/payment.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum

# =====================================================
# ENUMS
# =====================================================

class SubscriptionTierEnum(str, Enum):
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"

# =====================================================
# PRICING CONFIGURATION (INR - Paise)
# =====================================================

class PricingInfo(BaseModel):
    name: str
    price_cents: int  # In paise (₹29 = 2900 paise)
    campaign_limit: int
    features: List[str]

# Pricing in PAISE (₹1 = 100 paise)
PRICING_TIERS = {
    SubscriptionTierEnum.FREE: PricingInfo(
        name="Free",
        price_cents=0,
        campaign_limit=3,
        features=[
            "3 campaigns per month",
            "Basic targeting",
            "Facebook & Instagram only",
            "Email support"
        ]
    ),
    SubscriptionTierEnum.STARTER: PricingInfo(
        name="Starter",
        price_cents=2900,  # ₹29
        campaign_limit=10,
        features=[
            "10 campaigns per month",
            "All platforms",
            "Advanced targeting",
            "Priority support",
            "Campaign analytics"
        ]
    ),
    SubscriptionTierEnum.PROFESSIONAL: PricingInfo(
        name="Professional",
        price_cents=9900,  # ₹99
        campaign_limit=50,
        features=[
            "50 campaigns per month",
            "All platforms",
            "Advanced AI targeting",
            "API access",
            "Custom audience insights",
            "Priority support",
            "White-label options"
        ]
    ),
    SubscriptionTierEnum.ENTERPRISE: PricingInfo(
        name="Enterprise",
        price_cents=29900,  # ₹299
        campaign_limit=999999,  # Unlimited
        features=[
            "Unlimited campaigns",
            "All platforms",
            "Custom AI models",
            "Dedicated account manager",
            "API access",
            "Custom integrations",
            "24/7 support",
            "SLA guarantee"
        ]
    )
}

# Credits pricing (in paise)
CREDIT_PRICING = {
    10: 1000,      # ₹10
    50: 4000,      # ₹40 (20% discount)
    100: 7500,     # ₹75 (25% discount)
    500: 35000,    # ₹350 (30% discount)
    1000: 60000,   # ₹600 (40% discount)
}

# =====================================================
# REQUEST/RESPONSE MODELS
# =====================================================

class UserRegisterRequest(BaseModel):
    email: str
    password: str
    name: str

class UserLoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Optional[Dict] = None

class SubscriptionResponse(BaseModel):
    tier: str
    status: str
    expires_at: Optional[datetime] = None
    credits_balance: int
    total_campaigns_created: int
    stripe_subscription_id: Optional[str] = None

class CancelSubscriptionRequest(BaseModel):
    reason: Optional[str] = None

class PaymentHistoryItem(BaseModel):
    id: int
    amount_cents: int
    currency: str
    status: str
    description: Optional[str]
    credits_purchased: Optional[int]
    created_at: datetime
    
    class Config:
        from_attributes = True

class PaymentHistoryResponse(BaseModel):
    payments: List[PaymentHistoryItem]
    total_spent_cents: int

class CreditPackage(BaseModel):
    credits: int
    price_cents: int
    discount_percent: int = 0

def get_credits_packages() -> List[CreditPackage]:
    """Get all credit packages with calculated discounts"""
    base_price_per_credit = 100  # ₹1 per credit (100 paise)
    
    packages = []
    for credits, price_paise in CREDIT_PRICING.items():
        expected_price = credits * base_price_per_credit
        discount = int(((expected_price - price_paise) / expected_price) * 100) if expected_price > price_paise else 0
        
        packages.append(CreditPackage(
            credits=credits,
            price_cents=price_paise,
            discount_percent=discount
        ))
    
    return packages