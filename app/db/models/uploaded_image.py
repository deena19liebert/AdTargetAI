# app/db/models/uploaded_image.py
from sqlalchemy import Column, String, DateTime, JSON, Integer
from sqlalchemy.sql import func
from app.db.base import Base

class UploadedImage(Base):
    __tablename__ = "uploaded_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=True)
    path = Column(String(1024), nullable=True)
    url = Column(String(1024), nullable=True)
    mime = Column(String(50), nullable=True)
    extra_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)