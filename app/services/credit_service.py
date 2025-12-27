# app/services/credit_service.py
"""
Service for managing user credits and transactions
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from typing import Optional, Dict, Any
import logging

from app.db.models.user import User
from app.core.credits_config import (
    calculate_campaign_cost,
    MIN_CREDITS_REQUIRED,
    LOW_BALANCE_THRESHOLD
)

logger = logging.getLogger(__name__)

class CreditService:
    """Manage credit operations for users"""
    
    async def check_balance(
        self, 
        user: User, 
        required_credits: int
    ) -> Dict[str, Any]:
        """
        Check if user has sufficient credits
        
        Returns:
            Dict with status and messages
        """
        has_enough = user.credits_balance >= required_credits
        is_low = user.credits_balance <= LOW_BALANCE_THRESHOLD
        
        return {
            "has_enough": has_enough,
            "current_balance": user.credits_balance,
            "required": required_credits,
            "after_deduction": user.credits_balance - required_credits if has_enough else user.credits_balance,
            "is_low_balance": is_low,
            "message": self._get_balance_message(user.credits_balance, required_credits, has_enough)
        }
    
    def _get_balance_message(self, balance: int, required: int, has_enough: bool) -> str:
        """Generate user-friendly balance message"""
        if not has_enough:
            shortage = required - balance
            return f"Insufficient credits. You need {shortage} more credits."
        elif balance <= LOW_BALANCE_THRESHOLD:
            return f"Low balance warning! You have {balance} credits remaining."
        else:
            return f"You have {balance} credits available."
    
    async def deduct_credits(
        self,
        user: User,
        session: AsyncSession,
        amount: int,
        description: str = "Campaign creation"
    ) -> Dict[str, Any]:
        """
        Deduct credits from user account
        
        Args:
            user: User object
            session: Database session
            amount: Credits to deduct
            description: Reason for deduction
            
        Returns:
            Transaction details
            
        Raises:
            ValueError: If insufficient credits
        """
        if user.credits_balance < amount:
            raise ValueError(
                f"Insufficient credits. Required: {amount}, Available: {user.credits_balance}"
            )
        
        # Store old balance for logging
        old_balance = user.credits_balance
        
        # Deduct credits
        user.credits_balance -= amount
        
        # Commit to database
        await session.commit()
        await session.refresh(user)
        
        logger.info(
            f"✅ Deducted {amount} credits from user {user.id} "
            f"(Balance: {old_balance} → {user.credits_balance}) "
            f"Reason: {description}"
        )
        
        return {
            "success": True,
            "amount_deducted": amount,
            "old_balance": old_balance,
            "new_balance": user.credits_balance,
            "description": description,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def refund_credits(
        self,
        user: User,
        session: AsyncSession,
        amount: int,
        reason: str = "Campaign failed"
    ) -> Dict[str, Any]:
        """
        Refund credits to user account
        
        Args:
            user: User object
            session: Database session
            amount: Credits to refund
            reason: Reason for refund
            
        Returns:
            Refund details
        """
        old_balance = user.credits_balance
        
        # Add credits back
        user.credits_balance += amount
        
        await session.commit()
        await session.refresh(user)
        
        logger.info(
            f"💰 Refunded {amount} credits to user {user.id} "
            f"(Balance: {old_balance} → {user.credits_balance}) "
            f"Reason: {reason}"
        )
        
        return {
            "success": True,
            "amount_refunded": amount,
            "old_balance": old_balance,
            "new_balance": user.credits_balance,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def add_bonus_credits(
        self,
        user: User,
        session: AsyncSession,
        amount: int,
        reason: str = "Subscription bonus"
    ) -> Dict[str, Any]:
        """
        Add bonus credits (from subscription or promotion)
        
        Args:
            user: User object
            session: Database session
            amount: Credits to add
            reason: Reason for bonus
            
        Returns:
            Bonus details
        """
        old_balance = user.credits_balance
        
        user.credits_balance += amount
        
        await session.commit()
        await session.refresh(user)
        
        logger.info(
            f"🎁 Added {amount} bonus credits to user {user.id} "
            f"(Balance: {old_balance} → {user.credits_balance}) "
            f"Reason: {reason}"
        )
        
        return {
            "success": True,
            "bonus_amount": amount,
            "old_balance": old_balance,
            "new_balance": user.credits_balance,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def calculate_campaign_credits(
        self,
        platforms: list,
        has_advanced_targeting: bool = False
    ) -> int:
        """
        Calculate credits needed for a campaign
        
        Args:
            platforms: List of platform names
            has_advanced_targeting: Whether using advanced targeting
            
        Returns:
            Credits required
        """
        return calculate_campaign_cost(platforms, has_advanced_targeting)
    
    async def get_recommended_topup(self, current_balance: int) -> Dict[str, Any]:
        """
        Get recommended credit package based on current balance
        
        Args:
            current_balance: User's current credit balance
            
        Returns:
            Recommended package details
        """
        # If very low, recommend small package
        if current_balance < 10:
            return {
                "credits": 50,
                "price_paise": 4000,
                "reason": "You're running low! This will cover ~3-5 campaigns"
            }
        # If moderate, recommend medium package
        elif current_balance < 50:
            return {
                "credits": 100,
                "price_paise": 7500,
                "reason": "Best value! This will cover ~6-10 campaigns"
            }
        # If high, recommend large package for bulk discount
        else:
            return {
                "credits": 500,
                "price_paise": 35000,
                "reason": "Power user package with maximum savings"
            }

# Global instance
credit_service = CreditService()