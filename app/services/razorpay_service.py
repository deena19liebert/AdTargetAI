# app/services/razorpay_service.py 
"""
Enhanced Razorpay service with subscription bonus credits
"""
import razorpay
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.db.models.payment import User, Payment, PaymentStatus, SubscriptionTier
from app.schemas.payment import SubscriptionTierEnum, PRICING_TIERS, CREDIT_PRICING
from app.core.credits_config import get_subscription_credit_bonus
from app.services.credit_service import credit_service

logger = logging.getLogger(__name__)

class RazorpayService:
    """Service for handling all Razorpay operations"""
    
    def __init__(self):
        self.key_id = settings.RAZORPAY_KEY_ID
        self.key_secret = settings.RAZORPAY_KEY_SECRET
        
        if not self.key_id or not self.key_secret:
            logger.warning("⚠️ Razorpay credentials not configured - payment features disabled")
            self.client = None
        else:
            self.client = razorpay.Client(auth=(self.key_id, self.key_secret))
            logger.info("✅ Razorpay client initialized")
    
    async def create_subscription_order(
        self,
        session: AsyncSession,
        user: User,
        tier: SubscriptionTierEnum
    ) -> Dict[str, Any]:
        """Create Razorpay order for subscription"""
        
        if tier == SubscriptionTierEnum.FREE:
            raise ValueError("Cannot create order for free tier")
        
        if not self.client:
            raise ValueError("Razorpay not configured")
        
        pricing = PRICING_TIERS[tier]
        
        # Create Razorpay order
        order_data = {
            "amount": pricing.price_cents,
            "currency": "INR",
            "receipt": f"sub_{user.id}_{tier.value}_{int(datetime.utcnow().timestamp())}",
            "notes": {
                "user_id": str(user.id),
                "tier": tier.value,
                "type": "subscription"
            }
        }
        
        try:
            order = self.client.order.create(data=order_data)
            
            # Calculate bonus credits for this tier
            bonus_credits = get_subscription_credit_bonus(tier.value)
            
            logger.info(
                f"✅ Created Razorpay order {order['id']} for user {user.id}. "
                f"Will receive {bonus_credits} bonus credits on payment."
            )
            
            return {
                "order_id": order['id'],
                "amount": order['amount'],
                "currency": order['currency'],
                "key_id": self.key_id,
                "user_name": user.name,
                "user_email": user.email,
                "bonus_credits": bonus_credits  # Show user they'll get bonus credits
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to create Razorpay order: {e}")
            raise
    
    async def create_credits_order(
        self,
        session: AsyncSession,
        user: User,
        credits: int
    ) -> Dict[str, Any]:
        """Create Razorpay order for purchasing credits"""
        
        if credits not in CREDIT_PRICING:
            raise ValueError(f"Invalid credit amount: {credits}")
        
        if not self.client:
            raise ValueError("Razorpay not configured")
        
        # Apply subscription discount if applicable
        base_price = CREDIT_PRICING[credits]
        discount = 0
        
        if user.subscription_tier != SubscriptionTier.FREE:
            from app.core.credits_config import get_subscription_discount
            discount_percent = get_subscription_discount(user.subscription_tier.value)
            discount = int(base_price * discount_percent)
            logger.info(
                f"💰 Applying {discount_percent*100}% discount for {user.subscription_tier.value} tier"
            )
        
        final_price = base_price - discount
        
        order_data = {
            "amount": final_price,
            "currency": "INR",
            "receipt": f"credits_{user.id}_{credits}_{int(datetime.utcnow().timestamp())}",
            "notes": {
                "user_id": str(user.id),
                "credits": str(credits),
                "type": "credits_purchase",
                "original_price": str(base_price),
                "discount": str(discount)
            }
        }
        
        try:
            order = self.client.order.create(data=order_data)
            
            logger.info(
                f"✅ Created credits order {order['id']} for user {user.id}. "
                f"Credits: {credits}, Price: ₹{final_price/100:.2f} "
                f"(Discount: ₹{discount/100:.2f})"
            )
            
            return {
                "order_id": order['id'],
                "amount": order['amount'],
                "currency": order['currency'],
                "key_id": self.key_id,
                "user_name": user.name,
                "user_email": user.email,
                "credits": credits,
                "original_price": base_price,
                "discount": discount,
                "discount_percent": int((discount/base_price)*100) if discount > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to create credits order: {e}")
            raise
    
    async def verify_payment_signature(
        self,
        order_id: str,
        payment_id: str,
        signature: str
    ) -> bool:
        """Verify Razorpay payment signature"""
        
        if not self.client:
            raise ValueError("Razorpay not configured")
        
        try:
            params_dict = {
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': signature
            }
            
            self.client.utility.verify_payment_signature(params_dict)
            logger.info(f"✅ Payment signature verified for order {order_id}")
            return True
            
        except razorpay.errors.SignatureVerificationError as e:
            logger.error(f"❌ Payment signature verification failed: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Error verifying payment: {e}")
            return False
    
    async def handle_subscription_payment(
        self,
        payment_id: str,
        order_id: str,
        signature: str,
        db_session: AsyncSession
    ) -> Dict[str, Any]:
        """Handle successful subscription payment + ADD BONUS CREDITS"""
        
        # Verify signature first
        is_valid = await self.verify_payment_signature(order_id, payment_id, signature)
        
        if not is_valid:
            raise ValueError("Invalid payment signature")
        
        try:
            payment = self.client.payment.fetch(payment_id)
            order = self.client.order.fetch(order_id)
            
            user_id = int(order['notes']['user_id'])
            tier = order['notes']['tier']
            
            # Get user
            result = await db_session.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                logger.error(f"❌ User {user_id} not found for payment")
                raise ValueError(f"User not found")
            
            # Update user subscription
            user.subscription_tier = SubscriptionTier(tier)
            user.subscription_status = "active"
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
            
            # 🎁 ADD BONUS CREDITS based on tier
            bonus_credits = get_subscription_credit_bonus(tier)
            if bonus_credits > 0:
                await credit_service.add_bonus_credits(
                    user=user,
                    session=db_session,
                    amount=bonus_credits,
                    reason=f"Subscription bonus: {tier}"
                )
            
            # Record payment
            payment_record = Payment(
                user_id=user_id,
                stripe_payment_intent_id=payment_id,
                amount_cents=payment['amount'],
                currency=payment['currency'].upper(),
                status=PaymentStatus.COMPLETED,
                description=f"Subscription: {tier} + {bonus_credits} bonus credits",
                payment_metadata={
                    "razorpay_payment_id": payment_id,
                    "razorpay_order_id": order_id,
                    "tier": tier,
                    "bonus_credits": bonus_credits
                }
            )
            db_session.add(payment_record)
            
            await db_session.commit()
            
            logger.info(
                f"🎉 Activated {tier} subscription for user {user_id}. "
                f"Bonus credits: {bonus_credits}"
            )
            
            return {
                "status": "success",
                "message": f"Subscription activated: {tier}",
                "user_id": user_id,
                "tier": tier,
                "bonus_credits": bonus_credits,
                "new_credit_balance": user.credits_balance
            }
            
        except Exception as e:
            logger.error(f"❌ Error processing subscription payment: {e}")
            await db_session.rollback()
            raise
    
    async def handle_credits_payment(
        self,
        payment_id: str,
        order_id: str,
        signature: str,
        db_session: AsyncSession
    ) -> Dict[str, Any]:
        """Handle successful credits payment"""
        
        # Verify signature
        is_valid = await self.verify_payment_signature(order_id, payment_id, signature)
        
        if not is_valid:
            raise ValueError("Invalid payment signature")
        
        try:
            payment = self.client.payment.fetch(payment_id)
            order = self.client.order.fetch(order_id)
            
            user_id = int(order['notes']['user_id'])
            credits = int(order['notes']['credits'])
            
            # Get user
            result = await db_session.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                logger.error(f"❌ User {user_id} not found for credits purchase")
                raise ValueError("User not found")
            
            # Add credits
            old_balance = user.credits_balance
            user.credits_balance += credits
            
            # Record payment
            payment_record = Payment(
                user_id=user_id,
                stripe_payment_intent_id=payment_id,
                amount_cents=payment['amount'],
                currency=payment['currency'].upper(),
                credits_purchased=credits,
                status=PaymentStatus.COMPLETED,
                description=f"Purchased {credits} credits",
                payment_metadata={
                    "razorpay_payment_id": payment_id,
                    "razorpay_order_id": order_id,
                    "credits": credits,
                    "discount": order['notes'].get('discount', '0')
                }
            )
            db_session.add(payment_record)
            
            await db_session.commit()
            
            logger.info(
                f"✅ Added {credits} credits to user {user_id} "
                f"(Balance: {old_balance} → {user.credits_balance})"
            )
            
            return {
                "status": "success",
                "message": f"Added {credits} credits",
                "user_id": user_id,
                "credits": credits,
                "new_balance": user.credits_balance
            }
            
        except Exception as e:
            logger.error(f"❌ Error processing credits payment: {e}")
            await db_session.rollback()
            raise
    
    async def cancel_subscription(
        self,
        session: AsyncSession,
        user: User
    ) -> bool:
        """Cancel user's subscription"""
        
        user.subscription_status = "cancelled"
        
        await session.commit()
        logger.info(f"✅ Cancelled subscription for user {user.id}")
        return True
    
    async def get_payment_details(self, payment_id: str) -> Dict[str, Any]:
        """Fetch payment details from Razorpay"""
        
        if not self.client:
            raise ValueError("Razorpay not configured")
        
        try:
            payment = self.client.payment.fetch(payment_id)
            return payment
        except Exception as e:
            logger.error(f"❌ Failed to fetch payment details: {e}")
            raise

# Global instance
razorpay_service = RazorpayService()