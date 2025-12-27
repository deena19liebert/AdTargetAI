# app/db/models/transaction.py
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base
import enum

class TransactionType(str, enum.Enum):
    CREDIT_PURCHASE = "credit_purchase"
    CREDIT_REFUND = "credit_refund"
    ADMIN_ADJUSTMENT = "admin_adjustment"

class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Transaction details
    transaction_type = Column(SQLEnum(TransactionType), nullable=False)
    status = Column(SQLEnum(TransactionStatus), nullable=False, server_default="pending")
    
    # Money & Credits
    amount_inr = Column(Float, nullable=False)  # Amount in INR
    credits_purchased = Column(Float, nullable=False)
    
    # Payment gateway details
    razorpay_order_id = Column(String(255), nullable=True, index=True)
    razorpay_payment_id = Column(String(255), nullable=True, index=True)
    razorpay_signature = Column(String(255), nullable=True)
    
    # Payment method (UPI, Card, Net Banking, etc.)
    payment_method = Column(String(50), nullable=True)
    
    # Additional metadata
    description = Column(String(500), nullable=True)
    failure_reason = Column(String(500), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="transactions")
    
    def __repr__(self):
        return f"<Transaction(id={self.id} user_id={self.user_id} status={self.status} amount={self.amount_inr} credits={self.credits_purchased})>"