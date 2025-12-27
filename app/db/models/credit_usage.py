# app/db/models/credit_usage.py
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base

class CreditUsage(Base):
    __tablename__ = "credit_usages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Credit details
    credits_used = Column(Float, nullable=False)
    action = Column(String(100), nullable=False)  # "campaign_generation", "export_facebook", "export_google", etc.
    
    # Metadata
    details = Column(JSON, nullable=True)  # Store additional info like platform, budget, etc.
    balance_before = Column(Float, nullable=True)
    balance_after = Column(Float, nullable=True)
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="credit_usages")
    campaign = relationship("Campaign", back_populates="credit_usages")
    
    def __repr__(self):
        return f"<CreditUsage(id={self.id} user_id={self.user_id} campaign_id={self.campaign_id} credits={self.credits_used} action={self.action})>"