from sqlalchemy import Column, Integer, String, DateTime, Float
from datetime import datetime
from database import Base


class Photo(Base):
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    saved_path = Column(String, nullable=False)
    main_color = Column(String, nullable=True)
    clothing_type = Column(String, nullable=True)
    detected_style = Column(String, nullable=True)

    taken_at = Column(DateTime, nullable=True)
    location_name = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class WardrobeItem(Base):
    __tablename__ = "wardrobe_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    color = Column(String, nullable=True)
    clothing_type = Column(String, nullable=True)
    style = Column(String, nullable=True)
    wear_count = Column(Integer, default=1)
    last_worn_at = Column(DateTime, default=datetime.utcnow)
    last_location = Column(String, nullable=True)