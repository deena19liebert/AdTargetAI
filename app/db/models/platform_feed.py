# app/db/models/platform_feed.py
import uuid
from sqlalchemy import Column, String, ForeignKey, JSON, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base

class PlatformFeed(Base):
    __tablename__ = "platform_feeds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = Column(String(50), nullable=False)
    feed_data = Column(JSON, nullable=True)
    
    # status tracking
    status = Column(String(50), server_default="created")
    export_status = Column(String(50), server_default="pending")  # pending, success, failed, partial
    export_details = Column(JSON, nullable=True)  # Store detailed export results
    exported_ids = Column(JSON, nullable=True)  # Platform-specific IDs
    last_export_attempt = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    
    provisional_id = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    campaign = relationship("Campaign", back_populates="platform_feeds")
    facebook = relationship("FacebookDetails", back_populates="platform_feed", uselist=False)
    export_logs = relationship("ExportLog", back_populates="platform_feed")
    
    def __repr__(self):
        return f"<PlatformFeed(id={self.id} platform={self.platform} campaign_id={self.campaign_id})>"