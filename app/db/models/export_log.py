# app/db/models/export_log.py
from sqlalchemy import Column, String, Boolean, DateTime, JSON, ForeignKey, Integer
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base

class ExportLog(Base):
    __tablename__ = "export_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_feed_id = Column(Integer, ForeignKey("platform_feeds.id", ondelete="CASCADE"), nullable=False, index=True)
    mode = Column(String(20))
    success = Column(Boolean, default=False)
    request_payload = Column(JSON)
    response = Column(JSON)
    error = Column(String(2000), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    platform_feed = relationship("PlatformFeed", back_populates="export_logs")