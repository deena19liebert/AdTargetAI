# app/middleware/subscription.py
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from typing import Optional
import logging

from app.db.session import get_async_session
from app.db.models.user import User, SubscriptionTier
from app.routers.auth import get_current_user

logger = logging.getLogger(__name__)

class SubscriptionChecker:
    """Check subscription limits and credits"""
    
    async def check_campaign_limit(self, user: User) -> bool:
        """Check if user has reached their monthly campaign limit"""
        
        # Reset counter if new month
        now = datetime.utcnow()
        if user.last_campaign_reset is None or (
            user.last_campaign_reset.month != now.month or 
            user.last_campaign_reset.year != now.year
        ):
            user.campaigns_this_month = 0
            user.last_campaign_reset = now
        
        # Check limits by tier
        limits = {
            SubscriptionTier.FREE: 3,
            SubscriptionTier.STARTER: 10,
            SubscriptionTier.PROFESSIONAL: 50,
            SubscriptionTier.ENTERPRISE: float('inf')  # Unlimited
        }
        
        limit = limits.get(user.subscription_tier, 3)
        
        if user.campaigns_this_month >= limit:
            return False
        
        return True
    
    async def check_subscription_active(self, user: User) -> bool:
        """Check if user's subscription is active"""
        
        if user.subscription_tier == SubscriptionTier.FREE:
            return True
        
        if user.subscription_status != "active":
            return False
        
        if user.subscription_expires_at and user.subscription_expires_at < datetime.utcnow():
            return False
        
        return True
    
    async def check_credits(self, user: User, required: int = 1) -> bool:
        """Check if user has enough credits"""
        return user.credits_balance >= required
    
    async def deduct_credits(self, user: User, session: AsyncSession, amount: int = 1):
        """Deduct credits from user"""
        if user.credits_balance < amount:
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient credits. Required: {amount}, Available: {user.credits_balance}"
            )
        
        user.credits_balance -= amount
        await session.commit()
        logger.info(f"Deducted {amount} credits from user {user.id}. New balance: {user.credits_balance}")
    
    async def increment_campaign_count(self, user: User, session: AsyncSession):
        """Increment user's campaign count"""
        user.campaigns_this_month += 1
        user.total_campaigns_created += 1
        await session.commit()
        logger.info(f"User {user.id} created campaign #{user.total_campaigns_created} (#{user.campaigns_this_month} this month)")


# =====================================================
# DEPENDENCY FUNCTIONS
# =====================================================

async def require_active_subscription(
    user_id: int = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
) -> User:
    """Require user to have active subscription"""
    
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    checker = SubscriptionChecker()
    is_active = await checker.check_subscription_active(user)
    
    if not is_active:
        raise HTTPException(
            status_code=402,
            detail="Subscription expired or inactive. Please renew your subscription."
        )
    
    return user


async def require_campaign_limit(
    user_id: int = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
) -> User:
    """Require user to be within campaign limits"""
    
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    checker = SubscriptionChecker()
    
    # Check subscription active
    is_active = await checker.check_subscription_active(user)
    if not is_active:
        raise HTTPException(
            status_code=402,
            detail="Subscription expired. Please renew to continue."
        )
    
    # Check campaign limit
    can_create = await checker.check_campaign_limit(user)
    if not can_create:
        raise HTTPException(
            status_code=429,
            detail=f"You've reached your monthly limit for {user.subscription_tier.value} tier. Upgrade or wait until next month."
        )
    
    return user


async def require_credits(
    required: int = 1,
    user_id: int = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
) -> User:
    """Require user to have sufficient credits"""
    
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    checker = SubscriptionChecker()
    has_credits = await checker.check_credits(user, required)
    
    if not has_credits:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient credits. Required: {required}, Available: {user.credits_balance}. Purchase more credits to continue."
        )
    
    return user


class FeatureAccess:
    """Check feature access based on subscription tier"""
    
    @staticmethod
    def can_use_advanced_targeting(user: User) -> bool:
        """Advanced targeting for Professional+ tiers"""
        return user.subscription_tier in [
            SubscriptionTier.PROFESSIONAL,
            SubscriptionTier.ENTERPRISE
        ]
    
    @staticmethod
    def can_use_api(user: User) -> bool:
        """API access for Professional+ tiers"""
        return user.subscription_tier in [
            SubscriptionTier.PROFESSIONAL,
            SubscriptionTier.ENTERPRISE
        ]
    
    @staticmethod
    def can_export_to_platform(user: User, platform: str) -> bool:
        """Platform export restrictions"""
        if user.subscription_tier == SubscriptionTier.FREE:
            # Free tier: Only Facebook/Instagram
            return platform.lower() in ["facebook", "instagram"]
        
        # Paid tiers: All platforms
        return True