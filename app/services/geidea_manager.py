from __future__ import annotations
import os
import uuid
from base64 import b64encode
from datetime import datetime
from typing import Optional
import json
import hmac
import hashlib

from fastapi import HTTPException
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import User, Payment
from app.database import get_db
from app.settings import settings


class GeideaManager:
    # Geidea Configuration (loaded from settings)
    PUBLIC_KEY = settings.geidea_public_key
    API_PASSWORD = settings.geidea_api_password
    API_BASE = settings.geidea_api_base
    SESSION_URL = f"{API_BASE}/payment-intent/api/v2/direct/session"
    
    # Application URLs - from settings
    SUCCESS_URL = settings.geidea_success_url
    CANCEL_URL = settings.geidea_cancel_url
    CALLBACK_URL = settings.geidea_callback_url

    def __init__(self, current_user: User, db: AsyncSession):
        self.current_user = current_user
        self.db = db

    async def create_payment_record(self, amount: float, currency: str) -> Payment:
        """Create a payment record in the database"""
        try:
            merchant_reference_id = str(uuid.uuid4())   #the guy that sells 
            
            payment = Payment(
                user_id=self.current_user.id,
                amount=amount,
                currency=currency,
                merchant_reference_id=merchant_reference_id,
                status="PENDING"
            )
            
            self.db.add(payment)
            await self.db.commit()
            await self.db.refresh(payment)
            
            return payment
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to create payment record: {str(e)}")

    def _format_amount_two_decimals(self, amount: float) -> str:
        """Format amount to 2 decimal places"""
        return f"{amount:.2f}"

    def _generate_signature(
        self,
        merchant_public_key: str,
        amount: float,
        currency: str,
        merchant_reference_id: str,
        api_password: str,
        timestamp: str,
    ) -> str:
        """Generate signature for Geidea API authentication"""
        amount_str = self._format_amount_two_decimals(amount)
        data = f"{merchant_public_key}{amount_str}{currency}{merchant_reference_id}{timestamp}"
        digest = hmac.new(api_password.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).digest()
        return b64encode(digest).decode("utf-8")

    async def create_geidea_session(self, payment: Payment, language: str = "en", *, order: dict | None = None, shipping_address: dict | None = None) -> str:
        """Create a session with Geidea API"""
        try:
            if not self.PUBLIC_KEY or not self.API_PASSWORD:
                raise HTTPException(
                    status_code=500, 
                    detail="Geidea credentials are not configured on the server"
                )

            timestamp = datetime.utcnow().strftime("%Y/%m/%d %H:%M:%S")
            signature = self._generate_signature(
                merchant_public_key=self.PUBLIC_KEY,
                amount=float(payment.amount),
                currency=payment.currency,
                merchant_reference_id=payment.merchant_reference_id,
                api_password=self.API_PASSWORD,
                timestamp=timestamp,
            )

            request_body: dict = {
                "amount": float(payment.amount),
                "currency": payment.currency,
                "merchantReferenceId": payment.merchant_reference_id,
                "timestamp": timestamp,
                "signature": signature,
                "callbackUrl": self.CALLBACK_URL,
                "language": language
            }

            # Optionally include order and shipping address details if provided
            if order:
                request_body["order"] = order
            if shipping_address:
                request_body["shippingAddress"] = shipping_address

            basic_auth = b64encode(f"{self.PUBLIC_KEY}:{self.API_PASSWORD}".encode("utf-8")).decode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Basic {basic_auth}",
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                try:
                    resp = await client.post(self.SESSION_URL, json=request_body, headers=headers)
                except httpx.HTTPError as exc:
                    raise HTTPException(status_code=502, detail=f"Failed to reach Geidea: {exc}")

            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=f"Geidea error: {resp.text}")

            data = resp.json()

            # Check for success response codes
            if (data.get("responseCode") != "000") or (data.get("detailedResponseCode") not in ("000", "00000", None)):
                message = data.get("detailedResponseMessage") or data.get("responseMessage") or "Unknown error"
                raise HTTPException(status_code=400, detail=f"Geidea create session failed: {message}")

            session_id = (data.get("session") or {}).get("id")
            if not session_id:
                raise HTTPException(status_code=500, detail="Missing session id from Geidea response")

            # Update payment record with session ID
            payment.geidea_session_id = session_id
            await self.db.commit()

            return session_id

        except HTTPException:
            raise
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to create Geidea session: {str(e)}")

    async def create_payment_session(self, amount: float, currency: str, language: str = "en", *, order: dict | None = None, shipping_address: dict | None = None) -> tuple[str, int]:
        """Create a complete payment session (database record + Geidea session)"""
        try:
            # Create payment record
            payment = await self.create_payment_record(amount, currency)
            # Persist optional payloads for reporting
            if order is not None:
                payment.order_payload = json.dumps(order)
            if shipping_address is not None:
                payment.shipping_address_payload = json.dumps(shipping_address)
            await self.db.commit()
            
            # Create Geidea session
            session_id = await self.create_geidea_session(payment, language, order=order, shipping_address=shipping_address)
            
            return session_id, payment.id

        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to create payment session: {str(e)}")

    async def get_payment_by_id(self, payment_id: int) -> Optional[Payment]:
        """Get payment record by ID"""
        try:
            result = await self.db.execute(
                select(Payment).where(Payment.id == payment_id, Payment.user_id == self.current_user.id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to retrieve payment: {str(e)}")
    @classmethod
    async def handle_webhook(cls, payload: dict, db: AsyncSession):
        """Handle Geidea webhook notifications based on new schema"""
        try:
            order_data = payload.get("order")
            if not order_data:
                raise ValueError("Invalid webhook: Missing 'order' data")

            merchant_reference_id = order_data.get("merchantReferenceId")
            order_id = order_data.get("orderId")
            status = order_data.get("status")  # "Success", "Failed", "Cancelled", etc.
            
            if not merchant_reference_id:
                raise ValueError("Merchant reference ID not found in webhook payload")

            # Find payment by merchant reference ID
            result = await db.execute(
                select(Payment).where(Payment.merchant_reference_id == merchant_reference_id)
            )
            payment = result.scalar_one_or_none()
            
            if not payment:
                raise ValueError(f"Payment with merchant reference ID {merchant_reference_id} not found")

            # Determine final payment status
            if status and status.lower() == "success":
                payment.status = "SUCCESS"
                payment.geidea_order_id = order_id
            elif status and status.lower() in ["failed", "declined"]:
                payment.status = "FAILED"
            elif status and status.lower() in ["cancelled", "canceled"]:
                payment.status = "CANCELLED"
            else:
                payment.status = "UNKNOWN"

            await db.commit()

        except Exception as e:
            await db.rollback()
            print(f"[Geidea Webhook] Error handling webhook: {e}")
            return
