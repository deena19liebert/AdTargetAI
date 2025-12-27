# app/api/v1/payments_razorpay.py
"""
Payment and credit system endpoints
Simplified version without external schema dependencies
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import Optional
from pydantic import BaseModel
import logging

from app.db.session import get_async_session
from app.db.models.user import User
from app.db.models.transaction import Transaction, TransactionType, TransactionStatus
from app.db.models.credit_usage import CreditUsage
from app.routers.auth import get_current_user
from app.core.config import settings

router = APIRouter(prefix="/api", tags=["payments", "credits"])
logger = logging.getLogger(__name__)

# =====================================================
# 📋 REQUEST/RESPONSE MODELS
# =====================================================

class CreditPurchaseRequest(BaseModel):
    package_name: str  # "starter", "basic", "pro", "enterprise"
    payment_confirmed: bool = False

# =====================================================
# 💳 CREDIT SYSTEM ENDPOINTS
# =====================================================

@router.get("/credits/packages")
async def get_credit_packages():
    """Get available credit packages (public endpoint)"""
    return {
        "packages": settings.CREDIT_PACKAGES,
        "credits_per_inr": settings.CREDITS_PER_INR,
        "free_credits_on_signup": settings.FREE_CREDITS_ON_SIGNUP,
        "costs": {
            "campaign_generation": settings.CREDITS_PER_CAMPAIGN_GENERATION,
            "export_facebook_real": settings.CREDITS_PER_EXPORT_REAL_FACEBOOK,
            "export_google_real": settings.CREDITS_PER_EXPORT_REAL_GOOGLE
        }
    }


@router.post("/credits/purchase")
async def purchase_credits(
    purchase_request: CreditPurchaseRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Purchase credits via manual UPI payment confirmation
    
    Flow:
    1. User selects package → Creates pending transaction
    2. User pays via UPI/PhonePe/Google Pay
    3. User confirms payment → Credits added to account
    
    For production: Integrate Razorpay webhook for automatic verification
    """
    try:
        # Get package details
        package = settings.CREDIT_PACKAGES.get(purchase_request.package_name)
        if not package:
            raise HTTPException(status_code=400, detail="Invalid package name")
        
        amount_inr = package["amount_inr"]
        total_credits = package["credits"]
        
        # Create transaction record
        transaction = Transaction(
            user_id=current_user.id,
            transaction_type=TransactionType.CREDIT_PURCHASE,
            status=TransactionStatus.PENDING,
            amount_inr=amount_inr,
            credits_purchased=total_credits,
            description=f"Credit purchase: {purchase_request.package_name} package"
        )
        
        session.add(transaction)
        await session.commit()
        await session.refresh(transaction)
        
        # If payment is confirmed (manual UPI payment made), process it
        if purchase_request.payment_confirmed:
            # Update transaction status
            transaction.status = TransactionStatus.SUCCESS
            transaction.payment_method = "UPI (Manual)"
            
            # Add credits to user
            current_user.credits_balance += total_credits
            current_user.total_credits_purchased += total_credits
            
            await session.commit()
            
            logger.info(f"✅ Credits added: {current_user.email} received {total_credits} credits")
            
            return {
                "status": "success",
                "message": "Credits added successfully!",
                "transaction_id": transaction.id,
                "credits_added": total_credits,
                "new_balance": current_user.credits_balance
            }
        else:
            # Payment not yet confirmed - return payment instructions
            return {
                "status": "pending",
                "message": "Transaction created. Please complete payment.",
                "transaction_id": transaction.id,
                "amount_inr": amount_inr,
                "credits_to_receive": total_credits,
                "payment_instructions": {
                    "method": "UPI / Bank Transfer / Cash",
                    "note": "After making payment, call this endpoint again with payment_confirmed=True",
                    "demo_note": "In production, integrate Razorpay for automatic verification"
                }
            }
    
    except Exception as e:
        await session.rollback()
        logger.exception("Credit purchase failed")
        raise HTTPException(status_code=500, detail=f"Purchase failed: {str(e)}")


@router.get("/credits/balance")
async def get_credit_balance(current_user: User = Depends(get_current_user)):
    """Get user's current credit balance"""
    return {
        "credits_balance": current_user.credits_balance,
        "total_purchased": current_user.total_credits_purchased,
        "total_used": current_user.total_credits_used,
        "low_credit_warning": current_user.credits_balance < settings.LOW_CREDIT_THRESHOLD,
        "campaigns_possible": int(current_user.credits_balance / settings.CREDITS_PER_CAMPAIGN_GENERATION)
    }


@router.get("/credits/history")
async def get_credit_history(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get user's credit usage history"""
    result = await session.execute(
        select(CreditUsage)
        .where(CreditUsage.user_id == current_user.id)
        .order_by(desc(CreditUsage.created_at))
        .limit(50)
    )
    usage_history = result.scalars().all()
    
    return {
        "usage_history": [
            {
                "id": usage.id,
                "credits_used": usage.credits_used,
                "action": usage.action,
                "campaign_id": usage.campaign_id,
                "balance_before": usage.balance_before,
                "balance_after": usage.balance_after,
                "created_at": usage.created_at.isoformat() if usage.created_at else None,
                "details": usage.details
            }
            for usage in usage_history
        ],
        "current_balance": current_user.credits_balance
    }


@router.get("/transactions/history")
async def get_transaction_history(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get user's transaction history"""
    result = await session.execute(
        select(Transaction)
        .where(Transaction.user_id == current_user.id)
        .order_by(desc(Transaction.created_at))
        .limit(50)
    )
    transactions = result.scalars().all()
    
    return {
        "transactions": [
            {
                "id": tx.id,
                "amount_inr": tx.amount_inr,
                "credits_purchased": tx.credits_purchased,
                "status": tx.status.value,
                "transaction_type": tx.transaction_type.value,
                "payment_method": tx.payment_method,
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
                "completed_at": tx.completed_at.isoformat() if tx.completed_at else None,
                "description": tx.description
            }
            for tx in transactions
        ]
    }