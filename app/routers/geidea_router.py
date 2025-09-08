from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.geidea_manager import GeideaManager
from app.models import User
from app.schemas import CreatePaymentRequest, CreatePaymentResponse, PaymentStatusResponse
from app.services.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/payments", tags=["geidea-payments"])


@router.post("/create-session", response_model=CreatePaymentResponse)
async def create_payment_session(
    payment_request: CreatePaymentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new payment session"""
    try:
        geidea_manager = GeideaManager(current_user, db)
        session_id, payment_id = await geidea_manager.create_payment_session(
            amount=payment_request.amount,
            currency=payment_request.currency,
            language=payment_request.language,
            order=payment_request.order,
            shipping_address=payment_request.shippingAddress
        )
        
        return CreatePaymentResponse(
            session_id=session_id,
            payment_id=payment_id
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status/{payment_id}", response_model=PaymentStatusResponse)
async def get_payment_status(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get payment status by ID"""
    try:
        geidea_manager = GeideaManager(current_user, db)
        payment = await geidea_manager.get_payment_by_id(payment_id)
        
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
        
        return PaymentStatusResponse(
            payment_id=payment.id,
            status=payment.status,
            amount=float(payment.amount),
            currency=payment.currency,
            merchant_reference_id=payment.merchant_reference_id,
            created_at=payment.created_at.isoformat()
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/webhook")
async def geidea_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Geidea webhook notifications"""
    try:
        payload = await request.json()
        await GeideaManager.handle_webhook(payload, db)
        return {"status": "success", "message": "Webhook processed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {str(e)}") 