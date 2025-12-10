# app/db/models/facebook_details.py - FIXED VERSION
from sqlalchemy import Column, String, Integer, JSON, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base

class FacebookDetails(Base):
    __tablename__ = 'facebook_details'

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_feed_id = Column(Integer, ForeignKey('platform_feeds.id', ondelete='CASCADE'), nullable=False, index=True)
    ad_account = Column(String(128), nullable=True)
    page_id = Column(String(64), nullable=True)
    targeting = Column(JSON, nullable=True)
    creative = Column(JSON, nullable=True)
    budget_cents = Column(Integer, nullable=True)
    scheduling = Column(JSON, nullable=True)
    exported_ids = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    platform_feed = relationship('PlatformFeed', back_populates='facebook')
