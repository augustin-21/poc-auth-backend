from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, func, UniqueConstraint
)
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_user_email"),)

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # 1-to-many relationship to payments (optional, but handy)
    payments = relationship("Payment", back_populates="user")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)

    # FK to your integer PK on users
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="payments")

    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="EGP", nullable=False)

    # Merchant reference (your internal UUID) //should be realted to merchant
    merchant_reference_id = Column(String(64), unique=True, index=True, nullable=False)

    # Geidea identifiers
    geidea_order_id = Column(String(64), unique=True, index=True, nullable=True)  # orderId from callback
    geidea_session_id = Column(String(64), nullable=True)  # session.id from create-session
    card_token = Column(String(64), nullable=True)         # tokenId (if cardOnFile=true)

    # Optional payloads
    order_payload = Column(String, nullable=True)
    shipping_address_payload = Column(String, nullable=True)

    status = Column(String(20), default="PENDING", nullable=False)  # PENDING / SUCCESS / FAILED / CANCELLED
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)