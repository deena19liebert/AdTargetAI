# app/db/models/campaign.py
from sqlalchemy import Column, String, Text, JSON, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base

class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(String(128), unique=True, index=True, nullable=False)
    product = Column(String(255), nullable=False)
    product_description = Column(Text, nullable=True)
    campaign_input = Column(JSON, nullable=True)
    audience_insights = Column(JSON, nullable=True)
    campaign_strategy = Column(JSON, nullable=True)
    exported_ids = Column(JSON, nullable=True)
    
    # status tracking
    status = Column(String(50), nullable=False, server_default="ready")
    meta_status = Column(JSON, nullable=True)  # Store detailed Meta platform status
    last_export_attempt = Column(DateTime(timezone=True), nullable=True)
    export_history = Column(JSON, nullable=True)  # Store export attempts history
    
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    platform_feeds = relationship(
        "PlatformFeed",
        back_populates="campaign",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    
    def __repr__(self):
        return f"<Campaign(id={self.id} campaign_id={self.campaign_id} product={self.product})>"