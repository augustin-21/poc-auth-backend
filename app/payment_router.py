from __future__ import annotations

from base64 import b64encode
from datetime import datetime
import hmac
import hashlib
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator
import httpx


router = APIRouter(prefix="/payments", tags=["payments"])


GEIDEA_PUBLIC_KEY = "2258188d-9b2e-4bbf-817a-bd74a85e0c9c"
GEIDEA_API_PASSWORD = "e8374eaa-a151-47a6-b967-99dc482ecaaf"
GEIDEA_API_BASE = "https://api.geidea.ae"
GEIDEA_SESSION_URL = f"{GEIDEA_API_BASE}/payment-intent/api/v2/direct/session"


class CreateSessionRequest(BaseModel):
    amount: float = Field(..., gt=0)
    currency: str = Field(..., min_length=3, max_length=3)
    merchantReferenceId: str | None = None
    language: str | None = None
    callbackUrl: str

    @validator("currency")
    def currency_upper(cls, v: str) -> str:
        return v.upper()


class CreateSessionResponse(BaseModel):
    sessionId: str


def _format_amount_two_decimals(amount: float) -> str:
    return f"{amount:.2f}"


def _generate_signature(
    merchant_public_key: str,
    amount: float,
    currency: str,
    merchant_reference_id: str | None,
    api_password: str,
    timestamp: str,
) -> str:
    amount_str = _format_amount_two_decimals(amount)
    merchant_reference_id = merchant_reference_id or ""
    data = f"{merchant_public_key}{amount_str}{currency}{merchant_reference_id}{timestamp}"
    digest = hmac.new(api_password.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).digest()
    return b64encode(digest).decode("utf-8")


@router.post("/create-session", response_model=CreateSessionResponse)
async def create_session(payload: CreateSessionRequest):
    if not GEIDEA_PUBLIC_KEY or not GEIDEA_API_PASSWORD:
        raise HTTPException(status_code=500, detail="Geidea credentials are not configured on the server")

    timestamp = datetime.utcnow().strftime("%Y/%m/%d %H:%M:%S")
    signature = _generate_signature(
        merchant_public_key=GEIDEA_PUBLIC_KEY,
        amount=payload.amount,
        currency=payload.currency,
        merchant_reference_id=payload.merchantReferenceId,
        api_password=GEIDEA_API_PASSWORD,
        timestamp=timestamp,
    )

    request_body = {
        "amount": payload.amount,
        "currency": payload.currency,
        "merchantReferenceId": payload.merchantReferenceId,
        "timestamp": timestamp,
        "signature": signature,
        "callbackUrl": payload.callbackUrl,
    }

    basic_auth = b64encode(f"{GEIDEA_PUBLIC_KEY}:{GEIDEA_API_PASSWORD}".encode("utf-8")).decode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {basic_auth}",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(GEIDEA_SESSION_URL, json=request_body, headers=headers)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to reach Geidea: {exc}")

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=f"Geidea error: {resp.text}")

    data = resp.json()

    # Expecting responseCode and detailedResponseCode to be "000" on success
    if (data.get("responseCode") != "000") or (data.get("detailedResponseCode") not in ("000", "00000", None)):
        message = data.get("detailedResponseMessage") or data.get("responseMessage") or "Unknown error"
        raise HTTPException(status_code=400, detail=f"Geidea create session failed: {message}")

    session_id = (data.get("session") or {}).get("id")
    if not session_id:
        raise HTTPException(status_code=500, detail="Missing session id from Geidea response")

    return CreateSessionResponse(sessionId=session_id)


