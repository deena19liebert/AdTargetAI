from fastapi import FastAPI, HTTPException, Request, Header, APIRouter, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, EmailStr 
import shutil
import base64
import uvicorn
import os, json, logging
import time
from datetime import datetime, timedelta
from collections import OrderedDict
import bcrypt
from typing import Optional, Dict, Any
from pathlib import Path
from dotenv import load_dotenv
import uuid
import asyncio
import magic 
from sqlalchemy import update
from fastapi import Depends
load_dotenv()

# === Local Imports ===
from app.core.config import settings
from app.core.models import CampaignInput
from app.input_parser.validator import InputValidator
from app.llm_reasoner.mistral_reasoner import MistralReasoner
from app.feed_generator.platform_generator import PlatformDataGenerator
from app.export_manager.platform_router import PlatformRouter
from sqlalchemy.exc import SQLAlchemyError
from app.db.models.platform_feed import PlatformFeed
from app.routers.auth import router as auth_router
from app.api.v1.payments_razorpay import router as payments_router
from app.routers.campaigns import router as campaigns_router

# DB imports
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_async_session
from app.crud import (
    create_campaign_and_store,
    create_platform_feed,
    save_facebook_details,
    log_export,
    save_uploaded_image,
    get_campaign_by_campaign_id,
    update_exported_ids, 
)

from app.auth.dependencies import get_current_user, check_user_credits
from app.auth.security import create_access_token, get_password_hash
from app.db.models.user import User
from app.db.models.transaction import TransactionType, TransactionStatus
from app.crud_user import (
    create_user,
    authenticate_user,
    get_user_by_email,
    update_last_login,
    create_transaction,
    update_transaction_status,
    record_credit_usage,
    get_user_transactions,
    get_user_credit_usage_history,
    update_user_credits
)

import app.crud as crud 

from app.core.errors import (
    AdTargetAIException,
    adtargetai_exception_handler,
    validation_exception_handler,
    sqlalchemy_exception_handler
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CAMPAIGN_DIR = DATA_DIR / "campaigns"
DATA_DIR.mkdir(exist_ok=True)
CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif'}
ALLOWED_MIMETYPES = {'image/jpeg', 'image/png', 'image/gif'}

# === Setup ===
validator = InputValidator()
reasoner = MistralReasoner()
feed_generator = PlatformDataGenerator()
platform_router = PlatformRouter()
router = APIRouter()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="AdTargetAI",
    version="3.0.0",
    description="AI-Powered Marketing Campaign Generator with Mistral-7B",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

app.add_exception_handler(AdTargetAIException, adtargetai_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
app.include_router(auth_router)
app.include_router(payments_router)
app.include_router(campaigns_router)
app.include_router(router, prefix="")

if settings.ENVIRONMENT == "production":
    allowed_origins = settings.ALLOWED_ORIGINS
else:
    allowed_origins = ["*"]  

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-KEY"],
    max_age=3600,
)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

campaigns_store: OrderedDict[str, tuple[Dict[str, Any], datetime]] = OrderedDict()
MAX_CACHE_SIZE = 1000
CACHE_TTL = timedelta(hours=24)

def get_from_cache(campaign_id: str) -> Optional[Dict[str, Any]]:
    """Get campaign from cache with TTL check"""
    if campaign_id in campaigns_store:
        data, timestamp = campaigns_store[campaign_id]
        if datetime.now() - timestamp < CACHE_TTL:
            # Move to end (LRU)
            campaigns_store.move_to_end(campaign_id)
            return data
        else:
            # Expired
            del campaigns_store[campaign_id]
    return None

def add_to_cache(campaign_id: str, data: Dict[str, Any]):
    """Add campaign to cache with LRU eviction"""
    # Remove oldest if at capacity
    if len(campaigns_store) >= MAX_CACHE_SIZE:
        campaigns_store.popitem(last=False)
    
    campaigns_store[campaign_id] = (data, datetime.now())
    
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    path = Path("static/favicon.ico")
    if path.exists():
        return FileResponse(path)
    # fallback tiny PNG 1x1
    png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAAWgmWQ0AAAAASUVORK5CYII="
    png_bytes = base64.b64decode(png_b64)
    return Response(content=png_bytes, media_type="image/png")

logger = logging.getLogger("adtargetai")
logging.basicConfig(level=logging.INFO)

# =====================================================
# 🔐 PYDANTIC MODELS FOR AUTH
# =====================================================

# class UserRegister(BaseModel):
#     email: EmailStr
#     password: str
#     username: Optional[str] = None
#     full_name: Optional[str] = None
#     company_name: Optional[str] = None

# class UserLogin(BaseModel):
#     email: EmailStr
#     password: str

# class TokenResponse(BaseModel):
#     access_token: str
#     token_type: str = "bearer"
#     user: dict

# class CreditPurchaseRequest(BaseModel):
#     package_name: str  # "starter", "basic", "pro", "enterprise"
#     payment_confirmed: bool = False 
    
# =====================================================
# 🧠 BASIC ROUTES
# =====================================================
@app.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request):
    return templates.TemplateResponse("pricing.html", {"request": request})

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serve the main web interface"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# =====================================================
# 🔐 AUTHENTICATION ENDPOINTS
# =====================================================

# @app.post("/api/auth/register", response_model=TokenResponse)
# async def register(
#     user_data: UserRegister,
#     session: AsyncSession = Depends(get_async_session)
# ):
#     """Register a new user"""
#     try:
#         # Check if user exists
#         existing_user = await get_user_by_email(session, user_data.email)
#         if existing_user:
#             raise HTTPException(status_code=400, detail="Email already registered")
        
#         # Create user with free signup credits
#         user = await create_user(
#             session=session,
#             email=user_data.email,
#             password=user_data.password,
#             username=user_data.username,
#             full_name=user_data.full_name,
#             company_name=user_data.company_name,
#             initial_credits=settings.FREE_CREDITS_ON_SIGNUP
#         )
        
#         await session.commit()
        
#         # Create access token
#         access_token = create_access_token(data={"sub": user.id})
        
#         logger.info(f"✅ New user registered: {user.email} with {settings.FREE_CREDITS_ON_SIGNUP} free credits")
        
#         return {
#             "access_token": access_token,
#             "token_type": "bearer",
#             "user": {
#                 "id": user.id,
#                 "email": user.email,
#                 "username": user.username,
#                 "credits_balance": user.credits_balance,
#                 "full_name": user.full_name
#             }
#         }
    
#     except ValueError as e:
#         raise HTTPException(status_code=400, detail=str(e))
#     except Exception as e:
#         await session.rollback()
#         logger.exception("Registration failed")
#         raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


# @app.post("/api/auth/login", response_model=TokenResponse)
# async def login(
#     credentials: UserLogin,
#     response: Response,
#     session: AsyncSession = Depends(get_async_session)
# ):
#     """Login user"""
#     user = await authenticate_user(session, credentials.email, credentials.password)
    
#     if not user:
#         raise HTTPException(
#             status_code=401,
#             detail="Incorrect email or password"
#         )
    
#     if not user.is_active:
#         raise HTTPException(
#             status_code=403,
#             detail="Account is inactive. Contact support."
#         )
    
#     # Update last login
#     await update_last_login(session, user)
#     await session.commit()
    
#     # Create access token
#     access_token = create_access_token(data={"sub": user.id})
    
#     # Set cookie (optional - for browser-based auth)
#     response.set_cookie(
#         key="access_token",
#         value=access_token,
#         httponly=True,
#         max_age=7 * 24 * 60 * 60,  # 7 days
#         samesite="lax"
#     )
    
#     logger.info(f"✅ User logged in: {user.email}")
    
#     return {
#         "access_token": access_token,
#         "token_type": "bearer",
#         "user": {
#             "id": user.id,
#             "email": user.email,
#             "username": user.username,
#             "credits_balance": user.credits_balance,
#             "full_name": user.full_name
#         }
#     }


# @app.post("/api/auth/logout")
# async def logout(response: Response):
#     """Logout user (clear cookie)"""
#     response.delete_cookie("access_token")
#     return {"message": "Logged out successfully"}


# @app.get("/api/auth/me")
# async def get_current_user_info(
#     current_user: User = Depends(get_current_user),
#     session: AsyncSession = Depends(get_async_session)
# ):
#     """Get current logged-in user info"""
#     return {
#         "id": current_user.id,
#         "email": current_user.email,
#         "username": current_user.username,
#         "full_name": current_user.full_name,
#         "company_name": current_user.company_name,
#         "credits_balance": current_user.credits_balance,
#         "total_credits_purchased": current_user.total_credits_purchased,
#         "total_credits_used": current_user.total_credits_used,
#         "is_active": current_user.is_active,
#         "created_at": current_user.created_at,
#         "last_login": current_user.last_login
#     }
    
# =====================================================
# 💳 CREDIT SYSTEM ENDPOINTS
# =====================================================

# @app.get("/api/credits/packages")
# async def get_credit_packages():
#     """Get available credit packages"""
#     return {
#         "packages": settings.CREDIT_PACKAGES,
#         "credits_per_inr": settings.CREDITS_PER_INR,
#         "free_credits_on_signup": settings.FREE_CREDITS_ON_SIGNUP,
#         "costs": {
#             "campaign_generation": settings.CREDITS_PER_CAMPAIGN_GENERATION,
#             "export_facebook_real": settings.CREDITS_PER_EXPORT_REAL_FACEBOOK,
#             "export_google_real": settings.CREDITS_PER_EXPORT_REAL_GOOGLE
#         }
#     }


# @app.post("/api/credits/purchase")
# async def purchase_credits(
#     purchase_request: CreditPurchaseRequest,
#     current_user: User = Depends(get_current_user),
#     session: AsyncSession = Depends(get_async_session)
# ):
#     """
#     Purchase credits
    
#     For now, this is a MANUAL process:
#     1. User selects a package
#     2. Server creates a pending transaction
#     3. User makes UPI payment manually
#     4. User confirms payment (sets payment_confirmed=True)
#     5. Admin/automated system verifies and completes transaction
    
#     In production, integrate with Razorpay for automatic verification.
#     """
#     try:
#         # Get package details
#         package = settings.CREDIT_PACKAGES.get(purchase_request.package_name)
#         if not package:
#             raise HTTPException(status_code=400, detail="Invalid package name")
        
#         amount_inr = package["amount_inr"]
#         total_credits = package["credits"]
        
#         # Create transaction record
#         transaction = await create_transaction(
#             session=session,
#             user_id=current_user.id,
#             amount_inr=amount_inr,
#             credits_purchased=total_credits,
#             description=f"Credit purchase: {purchase_request.package_name} package"
#         )
        
#         await session.commit()
        
#         # If payment is confirmed (manual UPI payment made), process it
#         if purchase_request.payment_confirmed:
#             # In production, you would verify payment through Razorpay webhook
#             # For now, we'll process it directly (DEMO MODE)
            
#             # Update transaction status
#             transaction = await update_transaction_status(
#                 session=session,
#                 transaction_id=transaction.id,
#                 status=TransactionStatus.SUCCESS,
#                 payment_method="UPI (Manual)"
#             )
            
#             # Add credits to user
#             await update_user_credits(session, current_user, total_credits)
#             await session.commit()
            
#             logger.info(f"✅ Credits added: {current_user.email} received {total_credits} credits")
            
#             return {
#                 "status": "success",
#                 "message": "Credits added successfully!",
#                 "transaction_id": transaction.id,
#                 "credits_added": total_credits,
#                 "new_balance": current_user.credits_balance
#             }
#         else:
#             # Payment not yet confirmed - return payment instructions
#             return {
#                 "status": "pending",
#                 "message": "Transaction created. Please complete payment.",
#                 "transaction_id": transaction.id,
#                 "amount_inr": amount_inr,
#                 "credits_to_receive": total_credits,
#                 "payment_instructions": {
#                     "method": "UPI / Bank Transfer / Cash",
#                     "note": "After making payment, call this endpoint again with payment_confirmed=True",
#                     "demo_note": "In production, integrate Razorpay for automatic verification"
#                 }
#             }
    
#     except Exception as e:
#         await session.rollback()
#         logger.exception("Credit purchase failed")
#         raise HTTPException(status_code=500, detail=f"Purchase failed: {str(e)}")


# @app.get("/api/credits/balance")
# async def get_credit_balance(current_user: User = Depends(get_current_user)):
#     """Get user's current credit balance"""
#     return {
#         "credits_balance": current_user.credits_balance,
#         "total_purchased": current_user.total_credits_purchased,
#         "total_used": current_user.total_credits_used,
#         "low_credit_warning": current_user.credits_balance < settings.LOW_CREDIT_THRESHOLD
#     }


# @app.get("/api/credits/history")
# async def get_credit_history(
#     current_user: User = Depends(get_current_user),
#     session: AsyncSession = Depends(get_async_session)
# ):
#     """Get user's credit usage history"""
#     usage_history = await get_user_credit_usage_history(session, current_user.id, limit=50)
    
#     return {
#         "usage_history": [
#             {
#                 "id": usage.id,
#                 "credits_used": usage.credits_used,
#                 "action": usage.action,
#                 "campaign_id": usage.campaign_id,
#                 "balance_before": usage.balance_before,
#                 "balance_after": usage.balance_after,
#                 "created_at": usage.created_at,
#                 "details": usage.details
#             }
#             for usage in usage_history
#         ],
#         "current_balance": current_user.credits_balance
#     }


# @app.get("/api/transactions/history")
# async def get_transaction_history(
#     current_user: User = Depends(get_current_user),
#     session: AsyncSession = Depends(get_async_session)
# ):
#     """Get user's transaction history"""
#     transactions = await get_user_transactions(session, current_user.id, limit=50)
    
#     return {
#         "transactions": [
#             {
#                 "id": tx.id,
#                 "amount_inr": tx.amount_inr,
#                 "credits_purchased": tx.credits_purchased,
#                 "status": tx.status.value,
#                 "transaction_type": tx.transaction_type.value,
#                 "payment_method": tx.payment_method,
#                 "created_at": tx.created_at,
#                 "completed_at": tx.completed_at,
#                 "description": tx.description
#             }
#             for tx in transactions
#         ]
#     }
    
# =====================================================
# ✅ VALIDATION & INSIGHTS
# =====================================================

@app.post("/api/validate-input")
async def validate_input(
    raw_input: dict,
    current_user: User = Depends(get_current_user)  # Requires authentication
):
    """Validate campaign input"""
    try:
        validated = validator.validate_input(raw_input)
        return {
            "status": "success",
            "validated_data": validated.dict(),
            "message": "Input validation successful"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/upload-image")
async def upload_image(
    request: Request,
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Handle image upload from the front-end.
    Saves file locally and returns absolute URL + (optional) image_hash.
    """

    try:
        # 1. Validate content type
        if image.content_type not in ALLOWED_MIMETYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported image type: {image.content_type}. Use JPG, PNG, or GIF."
            )

        # 2. Read file with size limit
        content = await image.read(MAX_FILE_SIZE + 1)
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
            )

        # 3. Verify file extension
        ext = Path(image.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file extension: {ext}"
            )

        # 4. Verify actual file type using magic numbers
        mime = magic.from_buffer(content, mime=True)
        if mime not in ALLOWED_MIMETYPES:
            raise HTTPException(
                status_code=400,
                detail=f"File content doesn't match extension. Detected: {mime}"
            )

        # 5. Generate secure random filename
        safe_name = f"{uuid.uuid4().hex}{ext}"
        save_path = UPLOAD_DIR / safe_name

        # 6. Save file
        with save_path.open("wb") as buffer:
            buffer.write(content)

        # 7. Generate URL
        upload_url = f"{request.base_url}uploads/{safe_name}"

        # 8. Save to database for tracking
        await save_uploaded_image(
            session,
            filename=image.filename,
            path=str(save_path),
            url=upload_url,
            mime=mime,
            metadata={"size": len(content), "uploaded_by": current_user.id}
        )
        await session.commit()

        return {
            "url": upload_url,
            "path": f"/uploads/{safe_name}",
            "size": len(content),
            "mime_type": mime
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Image upload failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Image upload failed: {str(e)}"
        )

        
@app.post("/api/generate-insights")
async def generate_insights(
    raw_input: dict,
    current_user: User = Depends(get_current_user)  # Requires authentication
):
    """Generate audience insights only"""
    try:
        validated_input = validator.validate_input(raw_input)
        insights = await reasoner.infer_audience_insights(validated_input)

        return {
            "status": "success",
            "validated_input": validated_input.dict(),
            "audience_insights": insights.dict(),
            "message": "AI audience analysis completed"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Insights generation failed: {str(e)}")


# ====================================================
# 🚀 MAIN CAMPAIGN GENERATOR
# =====================================================

@app.post("/api/generate-campaign")
async def generate_campaign(
    campaign_data: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    required_credits = settings.CREDITS_PER_CAMPAIGN_GENERATION
    if not current_user.has_sufficient_credits(required_credits):
        raise HTTPException(
            status_code=402,  # Payment Required
            detail=f"Insufficient credits. You need {required_credits} credits, but have {current_user.credits_balance}. Please purchase more credits."
        )
        
    try:
        logger.info(f"🚀 Generating campaign for user: {current_user.email}")

        # 1️⃣ Validate input
        validated_input = validator.validate_input(campaign_data)

        # 2️⃣ Generate audience insights
        audience_insights = await reasoner.infer_audience_insights(validated_input)

        # 3️⃣ Generate campaign strategy
        campaign_strategy = await reasoner.generate_campaign_strategy(
            validated_input, audience_insights
        )

        # 4️⃣ Generate platform feeds
        platform_feeds = feed_generator.generate_platform_feeds(
            validated_input.dict()
        )

        # 5️⃣ Generate campaign ID
        campaign_slug = (
            f"campaign_{validated_input.product_name.replace(' ', '_').lower()}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )

        # 6️⃣ Save ROOT campaign into DB (with auto-commit)
        async with session.begin():
            campaign = await create_campaign_and_store(
                session=session,
                campaign_slug=campaign_slug,
                product=validated_input.product_name,
                campaign_input=validated_input.dict(),
                audience_insights=audience_insights.dict(),
                campaign_strategy=campaign_strategy,
            )
            
            # Link campaign to user
            campaign.user_id = current_user.id
            session.add(campaign)


            for platform_name, payload in platform_feeds.items():
                await create_platform_feed(
                    session=session,
                    campaign_slug_or_id=campaign.id,    
                    platform=platform_name,
                    payload=payload
                )
            # 7️⃣ Deduct credits and record usage
            await record_credit_usage(
                session=session,
                user=current_user,
                credits_used=required_credits,
                action="campaign_generation",
                campaign_id=campaign.id,
                details={
                    "product_name": validated_input.product_name,
                    "platforms": [p.value for p in validated_input.platforms],
                    "daily_budget": validated_input.daily_budget
                }
            )
        
        await session.commit()

        # 7️⃣ Build JSON response
        complete_campaign = {
            "campaign_id": campaign_slug,
            "product": validated_input.product_name,
            "generated_at": datetime.now().isoformat(),
            "status": "ready",
            "campaign_input": validated_input.dict(),
            "audience_insights": audience_insights.dict(),
            "campaign_strategy": campaign_strategy,
            "platform_feeds": platform_feeds,
        }

        campaigns_store[campaign_slug] = complete_campaign

        logger.info(f"✅ Campaign generated for {current_user.email}. Credits deducted: {required_credits}. New balance: {current_user.credits_balance}")

        return {
            "status": "success",
            "campaign_id": campaign_slug,
            "data": complete_campaign,
            "message": "Campaign generated and stored in database"
        }

    except Exception as e:
        # No need for manual rollback - session.begin() handles it
        logger.exception(f"Campaign generation failed: {e}")
        raise HTTPException(
            status_code=400, 
            detail=f"Campaign generation failed: {str(e)}"
        )

# =====================================================
# 📦 CAMPAIGN MANAGEMENT
# =====================================================
@app.post("/api/reach-estimate")
async def reach_estimate(
    targeting: dict,
    current_user: User = Depends(get_current_user)
):
    """
    Calculate estimated audience reach using:
      1. Facebook Marketing API (if valid token exists)
      2. Fallback heuristic if API unavailable

    This handler is defensive and returns rich error info to help debug.
    """
    import aiohttp
    from app.core.config import settings

    # Normalize tokens / account id (strip whitespace that often sneaks in from .env)
    access_token = (getattr(settings, "FACEBOOK_ACCESS_TOKEN", None) or "").strip()
    ad_account = (getattr(settings, "FACEBOOK_AD_ACCOUNT_ID", None) or "").strip()

    logger.info("reach_estimate called; ad_account=%s token_present=%s", 
                ad_account or "<missing>", bool(access_token))

    # Quick sanity checks
    if not access_token:
        logger.warning("Facebook access token missing or empty - returning heuristic fallback")
        return {"estimated_reach": "50K–200K (AI heuristic fallback)", "reason": "missing_access_token"}

    if not ad_account:
        logger.warning("Facebook ad account id missing - returning heuristic fallback")
        return {"estimated_reach": "50K–200K (AI heuristic fallback)", "reason": "missing_ad_account"}

    # Ensure ad_account is normalized: Graph endpoints often expect act_<id>
    if not str(ad_account).startswith("act_"):
        ad_account = f"act_{ad_account}"

    # If caller passed a small targeting dict (age_min, age_max, geo_locations...) convert to FB targeting_spec
    if "targeting_spec" not in targeting:
        fb_targeting = {
            "age_min": targeting.get("age_min"),
            "age_max": targeting.get("age_max"),
            # expect geo_locations to be like {"countries": ["US"]}
            "geo_locations": targeting.get("geo_locations") or targeting.get("locations") or {"countries": targeting.get("countries") or ["US"]},
            "flexible_spec": targeting.get("flexible_spec") or targeting.get("interests") and [{"interests": [{"id": i.get("id") if isinstance(i, dict) else i, "name": (i.get("name") if isinstance(i, dict) else None)} for i in targeting.get("interests")]}]
        }
        # remove None entries
        fb_targeting = {k: v for k, v in fb_targeting.items() if v}
        targeting_spec = fb_targeting
    else:
        # If caller already provided targeting_spec as JSON/string/dict
        targeting_spec = targeting.get("targeting_spec")

    fb_url = f"https://graph.facebook.com/v18.0/{ad_account}/reachestimate"
    params = {
        "access_token": access_token,
        "targeting_spec": json.dumps(targeting_spec),
        "optimize_for": "REACH"
    }

    logger.debug("Calling Facebook ReachEstimate: url=%s params=%s", fb_url, {k: (v if k != "access_token" else "<redacted>") for k,v in params.items()})

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(fb_url, params=params, timeout=15) as resp:
                text = await resp.text()
                status = resp.status
                logger.debug("FB reach response status=%s body=%s", status, text[:1000])

                if status != 200:
                    # Return the raw response so you can inspect in UI / logs
                    return {
                        "estimated_reach": "50K–200K (FB API error fallback)",
                        "error": f"FB API returned status {status}",
                        "raw": text
                    }

                data = json.loads(text)
                # FB often returns fields like 'estimate_dau' or 'users' - try several names
                estimated = data.get("estimate_dau") or data.get("users") or data.get("data") or data.get("estimate_daily_unique_reach") or data
                return {
                    "estimated_reach": estimated,
                    "raw": data
                }
    except Exception as e:
        logger.exception("Exception calling FB reachestimate: %s", e)
        return {
            "estimated_reach": "50K–200K (network fallback)",
            "error": str(e)
        }

@app.get("/api/google-ads/health")
async def google_ads_health(
    current_user: User = Depends(get_current_user),  # ✅ ADDED AUTH PROTECTION
    session: AsyncSession = Depends(get_async_session)
):
    from app.export_manager.google_ads_exporter import GoogleAdsExporter
    exporter = GoogleAdsExporter()
    res = exporter.health_check()
    return res

@app.get("/api/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    current_user: User = Depends(get_current_user),  # ✅ ADDED AUTH PROTECTION
    session: AsyncSession = Depends(get_async_session)
):
    cached = get_from_cache(campaign_id)
    if cached:
        return cached

    # disk fallback
    disk_path = CAMPAIGN_DIR / f"{campaign_id}.json"
    if disk_path.exists():
        with open(disk_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            campaigns_store[campaign_id] = data
            return data

    # try DB (lazy import)
    try:
        from app import crud
        db_row = await crud.get_campaign_by_campaign_id(session, campaign_id)
    except Exception as e:
        logger.warning("Could not load campaign from DB: %s", e)
        db_row = None

    if not db_row:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if db_row.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You don't have access to this campaign")
    platform_feeds_dict = {}
    for feed in getattr(db_row, "platform_feeds", []) or []:
        platform_feeds_dict[feed.platform] = feed.feed_data

    campaign_data = {
        "campaign_id": db_row.campaign_id,
        "product": db_row.product,
        "generated_at": db_row.generated_at.isoformat() if db_row.generated_at else None,
        "status": db_row.status,
        "campaign_input": db_row.campaign_input,
        "audience_insights": db_row.audience_insights,
        "campaign_strategy": db_row.campaign_strategy,

        "platform_feeds": platform_feeds_dict,

        "exported_ids": db_row.exported_ids,
        "meta_status": db_row.meta_status,
        "last_export_attempt": db_row.last_export_attempt.isoformat()
            if db_row.last_export_attempt else None,
        "export_history": db_row.export_history,
    }
    add_to_cache(campaign_id, campaign_data)
    return campaign_data


@app.get("/api/campaigns/{campaign_id}/download")
async def download_campaign(
    campaign_id: str,
    current_user: User = Depends(get_current_user),  # ✅ ADDED AUTH PROTECTION
    session: AsyncSession = Depends(get_async_session)
):
    # get campaign from memory/disk/DB then stream file
    data = await get_campaign(campaign_id, session)
    os.makedirs("exports", exist_ok=True)
    file_path = f"exports/{campaign_id}.json"
    with open(file_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, default=str)
    return FileResponse(path=file_path, filename=f"{campaign_id}_campaign.json", media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{campaign_id}_campaign.json"'})


@app.get("/api/campaigns")
async def list_campaigns(
    current_user: User = Depends(get_current_user),  # ✅ ADDED AUTH PROTECTION
    session: AsyncSession = Depends(get_async_session)
):
    """List all campaigns for current user"""
    from sqlalchemy import select
    from app.db.models.campaign import Campaign
    
    query = (
        select(Campaign)
        .where(Campaign.user_id == current_user.id)
        .order_by(Campaign.generated_at.desc())
    )
    result = await session.execute(query)
    campaigns = result.scalars().all()
    
    return {
        "campaigns": [
            {
                "campaign_id": c.campaign_id,
                "product": c.product,
                "status": c.status,
                "generated_at": c.generated_at.isoformat() if c.generated_at else None
            }
            for c in campaigns
        ],
        "count": len(campaigns)
    }


# -------------------------
# Export endpoint
# -------------------------
@router.post("/api/export-campaign/{campaign_id}")
async def export_campaign(
    campaign_id: str,
    export_request: Optional[Dict[str, Any]] = None,
    x_api_key: Optional[str] = Header(None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    start_time = time.time()
    export_request = export_request or {}
    create_real_ads = bool(export_request.get("create_real_ads", False))

    # 1) load campaign from memory/disk/DB
    cached = get_from_cache(campaign_id)
    if cached:
        campaign_data = cached
    else:
        disk_path = CAMPAIGN_DIR / f"{campaign_id}.json"
        if disk_path.exists():
            with open(disk_path, "r", encoding="utf-8") as fh:
                campaign_data = json.load(fh)
        else:
            db_row = await crud.get_campaign_by_campaign_id(session, campaign_id)
            if db_row:
                # ✅ Check ownership
                if db_row.user_id != current_user.id:
                    raise HTTPException(status_code=403, detail="You don't have access to this campaign")
                    
                campaign_data = {
                    "campaign_id": db_row.campaign_id,
                    "product": db_row.product,
                    "campaign_input": db_row.campaign_input,
                    "audience_insights": db_row.audience_insights,
                    "campaign_strategy": db_row.campaign_strategy,
                    "platform_feeds": [pf for pf in (db_row.platform_feeds or [])],
                    "exported_ids": db_row.exported_ids,
                }
            else:
                campaign_data = None

    if not campaign_data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # 2) determine platforms (robust)
    pf = campaign_data.get("platform_feeds") or {}
    if isinstance(pf, dict):
        pf_keys = list(pf.keys())
    elif isinstance(pf, list):
        pf_keys = [p.platform for p in pf if getattr(p, "platform", None)]
    else:
        pf_keys = []

    platforms = export_request.get("platforms") or pf_keys or ["facebook"]
    if not isinstance(platforms, list):
        raise HTTPException(status_code=400, detail="Platforms must be a list")

    # 3) admin checks for real creation
    if create_real_ads:
        if not getattr(settings, "ALLOW_REAL_ADS", False):
            raise HTTPException(status_code=403, detail="Real ad creation disabled on server")
        if not x_api_key:
            raise HTTPException(status_code=401, detail="Missing admin key in X-API-KEY header")
        ok = False
        if getattr(settings, "ADMIN_KEY_HASH", None):
            try:
                ok = bcrypt.checkpw(x_api_key.encode(), settings.ADMIN_KEY_HASH.encode())
            except Exception:
                ok = False
        elif getattr(settings, "ADMIN_KEY", None):
            ok = (x_api_key == settings.ADMIN_KEY)
        if not ok:
            raise HTTPException(status_code=401, detail="Invalid admin key")

    # 4) call platform router
    try:
        results = await platform_router.export_to_platforms(
            campaign_data=campaign_data,
            platforms=platforms,
            create_real_ads=create_real_ads
        )
    except Exception as e:
        logger.exception("Platform router failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Platform router error: {str(e)}")

    # 5) Persist export metadata & logs
    db_row = await crud.get_campaign_by_campaign_id(session, campaign_id)
    if not db_row:
        raise HTTPException(status_code=404, detail="Campaign not found in database")
    
    aggregated_exported = db_row.exported_ids or {}
    
    try:
        async with session.begin_nested():  # Use savepoint for partial rollback
            for platform_name, res in (results or {}).items():
                # Create platform_feed row
                pf_row = await crud.create_platform_feed(
                    session, 
                    db_row.id, 
                    platform_name, 
                    payload=res.get("campaign_payload", {})
                )

                # For facebook, save details if present
                if platform_name == "facebook" and pf_row:
                    fb_details = {
                        "ad_account": (res.get("meta") or {}).get("ad_account"),
                        "page_id": (res.get("meta") or {}).get("page_id"),
                        "targeting": (res.get("campaign_payload") or {}).get("adset", {}).get("targeting"),
                        "creative": (res.get("campaign_payload") or {}).get("creative"),
                        "budget_cents": (res.get("campaign_payload") or {}).get("adset", {}).get("daily_budget"),
                        "scheduling": None,
                        "exported_ids": {k: res.get(k) for k in ("campaign_id","adset_id","creative_id","ad_id") if res.get(k)}
                    }
                    await crud.save_facebook_details(session, pf_row.id, fb_details)

                # Log export attempt
                await crud.log_export(
                    session, 
                    pf_row.id,
                    "real" if create_real_ads else "dry_run",
                    res.get("campaign_payload", {}),
                    res,
                    res.get("status") == "success",
                    error=None if res.get("status") == "success" else res.get("message")
                )

                exported_ids = {
                    k: res.get(k) 
                    for k in ("campaign_id", "adset_id", "creative_id", "ad_id") 
                    if res.get(k)
                }
                    
                # Update platform feed status
                await crud.update_platform_feed_export_status(
                    session,
                    pf_row.id,
                    res.get("status", "pending"),
                    export_details=res,
                    exported_ids=exported_ids,
                    error_message=res.get("message") if res.get("status") != "success" else None
                )

                # aggregate campaign-level exported ids if success
                if res.get("status") == "success":
                    aggregated_exported[platform_name] = exported_ids

            await crud.update_exported_ids(session, db_row, aggregated_exported)
        
        # Commit outer transaction
        await session.commit()
    
        # Update in-memory cache
        campaign_data["exported_ids"] = aggregated_exported
        add_to_cache(campaign_id, campaign_data)

    except Exception as e:
        logger.exception("Failed to persist export metadata: %s", e)
        await session.rollback()
        raise HTTPException(
            status_code=500, 
            detail=f"Database error during export persistence: {str(e)}"
        )

    execution_time = round(time.time() - start_time, 2)
    
    return {
        "status": "success",
        "campaign_id": campaign_id,
        "export_results": results,
        "message": f"Export completed for {len(platforms)} platform(s)",
        "execution_time": execution_time
    }
    
# =====================================================
# 📚 PLATFORM INFO
# =====================================================
@router.get("/api/export-formats/{campaign_id}")
async def get_export_formats(campaign_id: str, current_user: User = Depends(get_current_user), session = Depends(get_async_session)):
    """
    Returns all format-previews (Facebook, Instagram, etc.)
    for the campaign_id.
    """
    from app import crud
    
    db_campaign = await crud.get_campaign_by_campaign_id(session, campaign_id)
    if not db_campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return {
        "campaign_id": db_campaign.campaign_id,
        "product": db_campaign.product,
        "campaign_input": db_campaign.campaign_input,
        "audience_insights": db_campaign.audience_insights,
        "campaign_strategy": db_campaign.campaign_strategy,
        "exported_ids": db_campaign.exported_ids,
        "created_at": db_campaign.generated_at,
        "updated_at": db_campaign.updated_at,
    }

@app.get("/api/platforms")
async def get_supported_platforms():
    return {
        "platforms": [
            "facebook", "instagram", "tiktok", "youtube",
            "linkedin", "x", "snapchat", "google", "pinterest"
        ],
        "export_formats": ["json", "platform_specific"]
    }


# =====================================================
# 🚀 SERVER BOOT
# =====================================================

if __name__ == "__main__":
    os.makedirs("templates", exist_ok=True)
    os.makedirs("static", exist_ok=True)
    os.makedirs("exports", exist_ok=True)
    os.makedirs("uploads", exist_ok=True)

    print("🚀 Starting AdTargetAI Server...")
    print("🌐 Web Interface: http://localhost:8000")
    print("📚 API Docs: http://localhost:8000/api/docs")
    print("🤖 Using Mistral AI for advanced marketing intelligence")
    print("📱 Facebook API: Ready for real ad creation!")

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
