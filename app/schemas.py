from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional,List, Dict, Any
import json
from datetime import datetime


# --- User ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class PaymentRead(BaseModel):
    id: int
    amount: float
    currency: str
    merchant_reference_id: str
    geidea_order_id: Optional[str] = None
    geidea_session_id: Optional[str] = None
    card_token: Optional[str] = None
    order_payload: Optional[dict] = None
    shipping_address_payload: Optional[dict] = None
    status: str
    created_at: datetime

    class Config:
        orm_mode = True

    # Accept DB-stored JSON strings transparently
    @validator("order_payload", pre=True)
    def _parse_order_payload(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return None
        return v

    @validator("shipping_address_payload", pre=True)
    def _parse_shipping_payload(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return None
        return v


class UserRead(BaseModel):
    id: int
    email: str
    is_active: bool
    created_at: datetime
    payments: List[PaymentRead] = []   # 👈 include payments here

    class Config:
        orm_mode = True
# --- Tokens ---
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    sub: str | None = None  # user id as string

# --- Geidea Payment Schemas ---
class CreatePaymentRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Payment amount")
    currency: str = Field(default="AED", min_length=3, max_length=3, description="Currency code")
    language: str = Field(default="en", description="Language preference")
    # Optional extra data to be forwarded to Geidea create-session
    order: Optional[Dict[str, Any]] = Field(default=None, description="Order details object to pass to Geidea")
    shippingAddress: Optional[Dict[str, Any]] = Field(default=None, description="Shipping address object to pass to Geidea")

    @validator("currency")
    def currency_upper(cls, v: str) -> str:
        return v.upper()

class CreatePaymentResponse(BaseModel):
    session_id: str
    payment_id: int

class PaymentStatusResponse(BaseModel):
    payment_id: int
    status: str
    amount: float
    currency: str
    merchant_reference_id: str
    created_at: str
