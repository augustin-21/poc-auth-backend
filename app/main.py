from datetime import timedelta
from fastapi import FastAPI, Depends, HTTPException, status, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from .database import engine, Base, get_db
from . import schemas
from app.services.auth import (
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from .services.user_crud import create_user, authenticate_user
from app.models import User
# Replace the old payment_router import with the new one
from app.routers.geidea_router import router as geidea_router

# --- OAuth2 configuration ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

app = FastAPI(title="FastAPI + SQLite + JWT", version="1.0.0")

# --- CORS configuration ---
origins = [
    "http://localhost:5173",  # React Vite dev server
    "http://localhost:5174",  # React Vite dev server
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register the new Geidea router
app.include_router(geidea_router)

# --- Startup: create tables ---
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Ensure optional columns exist for dev SQLite without migrations
        await conn.exec_driver_sql(
            """
            PRAGMA table_info(payments);
            """
        )
        # Add columns if missing
        res = await conn.exec_driver_sql("PRAGMA table_info(payments);")
        cols = [r[1] for r in res]
        if "order_payload" not in cols:
            await conn.exec_driver_sql("ALTER TABLE payments ADD COLUMN order_payload TEXT;")
        if "shipping_address_payload" not in cols:
            await conn.exec_driver_sql("ALTER TABLE payments ADD COLUMN shipping_address_payload TEXT;")

# --- Health check ---
@app.get("/")
async def root():
    return {"status": "OK"}

# --- Auth: Register ---
@app.post("/auth/register", response_model=schemas.UserRead, status_code=201)
async def register(user_in: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    return await create_user(db, user_in)

# --- Auth: Login ---
@app.post("/auth/login")
async def login_for_access_token(
    response: Response,
    request: schemas.UserCreate,
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db, email=request.email, password=request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password."
        )

    # Create tokens
    access_token = create_access_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    refresh_token = create_refresh_token(subject=str(user.id))

    # Set refresh token as HttpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,  # Set to True in production
        samesite="strict",
        max_age=60 * 60 * 24 * 7,  # 7 days
        path='/auth/refresh'
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

# --- OAuth2 Token endpoint for Swagger ---
@app.post("/auth/token")
async def login_for_documentation(
    response: Response,
    request: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db, email=request.username, password=request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password."
        )

    access_token = create_access_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    refresh_token = create_refresh_token(subject=str(user.id))

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,  # Set to True in production
        samesite="strict",
        max_age=60 * 60 * 24 * 7
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

# --- Refresh token endpoint ---
@app.post("/auth/refresh")
async def refresh_access_token(request: Request):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    user_id = verify_refresh_token(refresh_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    new_access_token = create_access_token(
        subject=str(user_id),
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return {
        "access_token": new_access_token,
        "token_type": "bearer"
    }

# --- Payment callback endpoint for testing ---
@app.post("/payments/callback")
async def payment_callback(request: Request):
    """
    Callback endpoint for Geidea payment notifications.
    This is for testing purposes - in production you'd want to:
    1. Verify the signature from Geidea
    2. Update your database with payment status
    3. Send confirmation emails, etc.
    """
    try:
        # Get the raw body for signature verification (if needed)
        body = await request.body()
        
        # Parse JSON data
        data = await request.json()
        
        # Log the callback data (in production, use proper logging)
        print("=== PAYMENT CALLBACK RECEIVED ===")
        print(f"Response Code: {data.get('responseCode')}")
        print(f"Response Message: {data.get('responseMessage')}")
        print(f"Detailed Response Code: {data.get('detailedResponseCode')}")
        print(f"Detailed Response Message: {data.get('detailedResponseMessage')}")
        print(f"Order ID: {data.get('orderId')}")
        print(f"Reference: {data.get('reference')}")
        print(f"Amount: {data.get('amount')}")
        print(f"Currency: {data.get('currency')}")
        print("=================================")
        
        # In a real app, you would:
        # 1. Verify the signature from Geidea
        # 2. Update your database
        # 3. Send notifications to user
        
        return {"status": "received", "message": "Callback processed successfully"}
        
    except Exception as e:
        print(f"Error processing payment callback: {e}")
        return {"status": "error", "message": str(e)}

# --- Example protected route ---
@app.get("/users/me", response_model=schemas.UserRead)
async def read_me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).options(selectinload(User.payments)).where(User.id == current_user.id)
    )
    user = result.scalar_one()
    return user