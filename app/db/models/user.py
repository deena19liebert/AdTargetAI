# app/db/models/user.py
"""
Merged User model combining features from:
- Credit system (transactions, credit_usage)
- Payment system (razorpay, subscriptions, connected accounts)
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, Enum as SQLEnum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base
import enum

class SubscriptionTier(str, enum.Enum):
    """Subscription tiers for the platform"""
    FREE = "free"
    STARTER = "starter"  # $29/month - 10 campaigns
    PROFESSIONAL = "professional"  # $99/month - 50 campaigns
    ENTERPRISE = "enterprise"  # $299/month - unlimited

class User(Base):
    """
    Unified User model with:
    - Authentication (email, password)
    - Credit system (credits_balance, transactions)
    - Subscription system (Razorpay, tiers)
    - Campaign tracking
    """
    __tablename__ = "users"

    # ==================== PRIMARY KEY ====================
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # ==================== AUTHENTICATION ====================
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=False)
    
    # ==================== CREDIT SYSTEM (NEW) ====================
    credits_balance = Column(Float, nullable=False, server_default="0.0")
    total_credits_purchased = Column(Float, nullable=False, server_default="0.0")
    total_credits_used = Column(Float, nullable=False, server_default="0.0")
    
    # ==================== RAZORPAY INTEGRATION (OLD) ====================
    razorpay_customer_id = Column(String(255), unique=True, index=True, nullable=True)
    razorpay_subscription_id = Column(String(255), unique=True, nullable=True)
    
    # ==================== SUBSCRIPTION SYSTEM (OLD) ====================
    subscription_tier = Column(SQLEnum(SubscriptionTier), default=SubscriptionTier.FREE)
    subscription_status = Column(String(50), default="inactive")
    subscription_expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # ==================== CAMPAIGN TRACKING (OLD) ====================
    total_campaigns_created = Column(Integer, default=0, nullable=False)
    campaigns_this_month = Column(Integer, default=0, nullable=False)
    last_campaign_reset = Column(DateTime(timezone=True), nullable=True)
    
    # ==================== USER METADATA ====================
    full_name = Column(String(200), nullable=True)
    name = Column(String(255), nullable=True)  # Alias for full_name (for compatibility)
    company_name = Column(String(200), nullable=True)
    phone = Column(String(20), nullable=True)
    
    # ==================== ACCOUNT STATUS ====================
    is_active = Column(Boolean, nullable=False, server_default="true")
    is_verified = Column(Boolean, nullable=False, server_default="false")
    
    # ==================== TIMESTAMPS ====================
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)
    
    # ==================== RELATIONSHIPS ====================
    # Credit system relationships (NEW)
    campaigns = relationship("Campaign", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    credit_usages = relationship("CreditUsage", back_populates="user", cascade="all, delete-orphan")
    
    # Payment system relationships (OLD)
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    connected_accounts = relationship("ConnectedAdAccount", back_populates="user", cascade="all, delete-orphan")
    
    # ==================== METHODS ====================
    def __repr__(self):
        return f"<User(id={self.id} email={self.email} credits={self.credits_balance})>"
    
    def has_sufficient_credits(self, required_credits: float) -> bool:
        """Check if user has enough credits"""
        return self.credits_balance >= required_credits
    
    def deduct_credits(self, amount: float):
        """Deduct credits from user balance"""
        if amount <= 0:
            raise ValueError("Credit amount must be positive")
        if not self.has_sufficient_credits(amount):
            raise ValueError(f"Insufficient credits. Available: {self.credits_balance}, Required: {amount}")
        self.credits_balance -= amount
        self.total_credits_used += amount
    
    def add_credits(self, amount: float):
        """Add credits to user balance"""
        if amount <= 0:
            raise ValueError("Credit amount must be positive")
        self.credits_balance += amount
        self.total_credits_purchased += amount