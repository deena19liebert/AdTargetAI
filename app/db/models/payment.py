# app/db/models/payment.py
"""
Payment system models (WITHOUT User - User is in user.py)
Includes: Payment, ConnectedAdAccount, PaymentStatus enum
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base
import enum

class PaymentStatus(str, enum.Enum):
    """Payment status for Razorpay transactions"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"

class Payment(Base):
    """
    Payment records for Razorpay transactions
    Note: This is SEPARATE from the Transaction model (which tracks credits)
    """
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Razorpay IDs
    stripe_payment_intent_id = Column(String(255), unique=True, nullable=True)  # Reusing for Razorpay
    razorpay_order_id = Column(String(255), nullable=True)

    # Payment details
    amount_cents = Column(Integer, nullable=False)  # Store in cents
    currency = Column(String(3), default="INR")
    credits_purchased = Column(Integer, nullable=True)  # If buying credits

    # Status
    status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING)
    payment_method = Column(String(50), nullable=True)
    description = Column(String(500), nullable=True)
    payment_metadata = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationship
    user = relationship("User", back_populates="payments")


class ConnectedAdAccount(Base):
    """Store user's connected ad accounts (Facebook, Google, TikTok)"""
    __tablename__ = "connected_ad_accounts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    platform = Column(String(50), nullable=False)  # facebook, google, tiktok

    # Platform-specific IDs
    platform_account_id = Column(String(255), nullable=False)
    platform_account_name = Column(String(255), nullable=True)

    # OAuth tokens (encrypt in production!)
    access_token = Column(String(1000), nullable=True)
    refresh_token = Column(String(1000), nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    last_synced = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    user = relationship("User", back_populates="connected_accounts")