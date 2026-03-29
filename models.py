from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    photos = relationship("Photo", back_populates="user")
    wardrobe_items = relationship("WardrobeItem", back_populates="user")

class Photo(Base):
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    saved_path = Column(String)
    main_color = Column(String)
    clothing_type = Column(String)
    detected_style = Column(String)
    taken_at = Column(DateTime, nullable=True)
    location_name = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    user = relationship("User", back_populates="photos")

class WardrobeItem(Base):
    __tablename__ = "wardrobe_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    color = Column(String)
    clothing_type = Column(String)
    style = Column(String)
    wear_count = Column(Integer, default=1)
    last_worn_at = Column(DateTime, nullable=True)
    last_location = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    user = relationship("User", back_populates="wardrobe_items")
    