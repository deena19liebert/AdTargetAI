# app/routers/campaigns.py
"""
Campaign creation router with credit-based payment integration
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import logging

from app.db.session import get_async_session
from app.db.models.user import User 
from app.routers.auth import get_current_user
from app.middleware.subscription import SubscriptionChecker, require_campaign_limit
from app.services.credit_service import credit_service
from app.schemas.campaign import (
    CampaignCreateRequest,
    CampaignCreateResponse,
    CreditCheckResponse
)

router = APIRouter(prefix="/api/campaigns", tags=["Campaigns"])
logger = logging.getLogger(__name__)

# =====================================================
# 💳 CREDIT CHECK BEFORE CAMPAIGN CREATION
# =====================================================

@router.post("/check-credits", response_model=CreditCheckResponse)
async def check_campaign_credits(
    request: CampaignCreateRequest,
    user_id: int = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Check if user has enough credits for campaign creation.
    Call this BEFORE showing campaign creation confirmation.
    """
    
    # Get user
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Calculate required credits
    required_credits = credit_service.calculate_campaign_credits(
        platforms=request.platforms,
        has_advanced_targeting=request.use_advanced_targeting
    )
    
    # Check balance
    balance_check = await credit_service.check_balance(user, required_credits)
    
    # Get recommended top-up if balance is low
    recommended_topup = None
    if not balance_check["has_enough"] or balance_check["is_low_balance"]:
        recommended_topup = await credit_service.get_recommended_topup(
            user.credits_balance
        )
    
    return CreditCheckResponse(
        has_enough_credits=balance_check["has_enough"],
        current_balance=balance_check["current_balance"],
        required_credits=required_credits,
        balance_after=balance_check["after_deduction"],
        is_low_balance=balance_check["is_low_balance"],
        message=balance_check["message"],
        recommended_topup=recommended_topup
    )

# =====================================================
# 🚀 CREATE CAMPAIGN (WITH CREDIT DEDUCTION)
# =====================================================

@router.post("/create", response_model=CampaignCreateResponse)
async def create_campaign(
    request: CampaignCreateRequest,
    user: User = Depends(require_campaign_limit),  # Check subscription limits
    session: AsyncSession = Depends(get_async_session)
):
    """
    Create a new ad campaign across specified platforms.
    
    Flow:
    1. Calculate credit cost
    2. Check user balance
    3. Deduct credits (reserve)
    4. Call platform APIs (Meta, Google, etc.)
    5. If success: Confirm deduction, increment campaign count
    6. If failure: Refund credits, return error
    """
    
    # STEP 1: Calculate cost
    required_credits = credit_service.calculate_campaign_credits(
        platforms=request.platforms,
        has_advanced_targeting=request.use_advanced_targeting
    )
    
    logger.info(f"User {user.id} creating campaign. Required credits: {required_credits}")
    
    # STEP 2: Check balance
    balance_check = await credit_service.check_balance(user, required_credits)
    
    if not balance_check["has_enough"]:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_credits",
                "message": balance_check["message"],
                "required": required_credits,
                "current": user.credits_balance,
                "shortage": required_credits - user.credits_balance
            }
        )
    
    # STEP 3: Deduct credits BEFORE API calls
    try:
        deduction = await credit_service.deduct_credits(
            user=user,
            session=session,
            amount=required_credits,
            description=f"Campaign: {request.product_name} on {', '.join(request.platforms)}"
        )
        
        logger.info(f"✅ Credits deducted: {deduction}")
        
    except ValueError as e:
        raise HTTPException(status_code=402, detail=str(e))
    
    # STEP 4: Call Platform APIs
    platform_responses = {}
    deployed_platforms = []
    warnings = []
    
    try:
        # TODO: Replace with your actual API calls
        for platform in request.platforms:
            try:
                if platform.lower() in ["facebook", "instagram"]:
                    # Call Meta API
                    response = await _create_meta_campaign(request, user)
                    platform_responses[platform] = response
                    deployed_platforms.append(platform)
                    
                elif platform.lower() == "google":
                    # Call Google Ads API
                    response = await _create_google_campaign(request, user)
                    platform_responses[platform] = response
                    deployed_platforms.append(platform)
                    
                # Add more platforms...
                else:
                    warnings.append(f"Platform '{platform}' not yet supported")
                    
            except Exception as e:
                logger.error(f"❌ Failed to create campaign on {platform}: {e}")
                warnings.append(f"Failed on {platform}: {str(e)}")
        
        # If NO platforms succeeded, refund and fail
        if not deployed_platforms:
            await credit_service.refund_credits(
                user=user,
                session=session,
                amount=required_credits,
                reason="All platforms failed"
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to deploy campaign on any platform. Credits refunded."
            )
        
        # STEP 5: Update campaign count
        checker = SubscriptionChecker()
        await checker.increment_campaign_count(user, session)
        
        logger.info(f"🎉 Campaign created successfully for user {user.id}")
        
        return CampaignCreateResponse(
            success=True,
            message=f"Campaign deployed successfully on {len(deployed_platforms)} platform(s)",
            campaign_id=f"camp_{user.id}_{int(user.total_campaigns_created)}",
            credits_deducted=required_credits,
            credits_remaining=user.credits_balance,
            platforms_deployed=deployed_platforms,
            platform_responses=platform_responses,
            warnings=warnings if warnings else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        # Unexpected error - refund credits
        logger.error(f"❌ Unexpected error creating campaign: {e}")
        
        await credit_service.refund_credits(
            user=user,
            session=session,
            amount=required_credits,
            reason=f"System error: {str(e)}"
        )
        
        raise HTTPException(
            status_code=500,
            detail=f"Campaign creation failed. Credits refunded. Error: {str(e)}"
        )

# =====================================================
# 🔌 PLATFORM API INTEGRATION HELPERS
# =====================================================

async def _create_meta_campaign(request: CampaignCreateRequest, user: User):
    """
    Create campaign on Meta (Facebook/Instagram)
    Replace this with your actual Meta API integration
    """
    # TODO: Implement actual Meta API call
    # from app.services.meta_service import meta_service
    # return await meta_service.create_campaign(request, user)
    
    # PLACEHOLDER
    logger.info(f"📘 Creating Meta campaign for user {user.id}")
    return {
        "platform": "meta",
        "status": "created",
        "campaign_id": "meta_123456",
        "message": "Campaign created on Facebook & Instagram"
    }

async def _create_google_campaign(request: CampaignCreateRequest, user: User):
    """
    Create campaign on Google Ads
    Replace this with your actual Google Ads API integration
    """
    # TODO: Implement actual Google Ads API call
    # from app.services.google_ads_service import google_ads_service
    # return await google_ads_service.create_campaign(request, user)
    
    # PLACEHOLDER
    logger.info(f"🔍 Creating Google Ads campaign for user {user.id}")
    return {
        "platform": "google",
        "status": "created",
        "campaign_id": "google_789012",
        "message": "Campaign created on Google Ads"
    }

# =====================================================
# 📊 CAMPAIGN MANAGEMENT ENDPOINTS
# =====================================================

@router.get("/my-campaigns")
async def get_my_campaigns(
    user_id: int = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get all campaigns for current user"""
    
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # TODO: Implement campaign storage and retrieval
    # For now, return basic stats
    return {
        "total_campaigns": user.total_campaigns_created,
        "campaigns_this_month": user.campaigns_this_month,
        "credits_balance": user.credits_balance,
        "subscription_tier": user.subscription_tier.value,
        "message": "Campaign history coming soon!"
    }

@router.get("/stats")
async def get_campaign_stats(
    user_id: int = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get campaign statistics for user"""
    
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "total_campaigns_created": user.total_campaigns_created,
        "campaigns_this_month": user.campaigns_this_month,
        "credits_balance": user.credits_balance,
        "subscription_tier": user.subscription_tier.value,
        "subscription_status": user.subscription_status,
        "is_low_balance": user.credits_balance < 20
    }