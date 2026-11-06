from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

MOTOR_STATUSES = ("in_stock", "sold")
ENQUIRY_STATUSES = ("new", "contacted", "sold", "closed")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Motor(Base):
    __tablename__ = "motors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    make: Mapped[str] = mapped_column(String(80), index=True)
    model: Mapped[Optional[str]] = mapped_column(String(80))
    year: Mapped[Optional[int]] = mapped_column(Integer)
    hp: Mapped[int] = mapped_column(Integer, index=True)
    stroke: Mapped[int] = mapped_column(Integer, index=True)
    cylinders: Mapped[Optional[int]] = mapped_column(Integer)
    shaft: Mapped[Optional[str]] = mapped_column(String(40))
    hours: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    price_usd: Mapped[Optional[int]] = mapped_column(Integer)
    condition: Mapped[Optional[str]] = mapped_column(String(40))
    badge: Mapped[Optional[str]] = mapped_column(String(40))
    image_url: Mapped[Optional[str]] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="in_stock", index=True)


class Enquiry(Base):
    __tablename__ = "enquiries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(40))
    motor_of_interest: Mapped[Optional[str]] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    shipping_zip: Mapped[Optional[str]] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    internal_notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
