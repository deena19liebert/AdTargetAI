# app/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel, EmailStr
import logging

from app.db.session import get_async_session
from app.db.models.user import User, SubscriptionTier
from app.core.config import settings

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = settings.JWT_SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# =====================================================
# 📋 REQUEST/RESPONSE MODELS
# =====================================================

class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str
    username: Optional[str] = None  # ✅ FIXED: Changed from 'name' to 'username'
    full_name: Optional[str] = None  # ✅ ADDED: To match User model
    company_name: Optional[str] = None  # ✅ ADDED: To match User model

class UserResponse(BaseModel):
    id: int
    email: str
    username: Optional[str] = None
    full_name: Optional[str] = None
    subscription_tier: str
    credits_balance: float
    
    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

# =====================================================
# 🔐 HELPER FUNCTIONS
# =====================================================

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
  
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_async_session)
) -> User:
    """Extract user from JWT token and return full User object"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Get full user from database
        result = await session.execute(select(User).where(User.id == int(user_id)))
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        if not user.is_active:
            raise HTTPException(status_code=403, detail="User account is inactive")
        
        return user
        
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# =====================================================
# 🔐 AUTHENTICATION ENDPOINTS
# =====================================================

@router.post("/register", response_model=TokenResponse)
async def register(
    request: UserRegisterRequest,
    session: AsyncSession = Depends(get_async_session)
):
    """Register new user with free signup credits"""
    
    # Check if user already exists
    result = await session.execute(select(User).where(User.email == request.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Validate password
    if len(request.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    
    # Create new user
    new_user = User(
        email=request.email,
        username=request.username,
        password_hash=get_password_hash(request.password),
        full_name=request.full_name,
        name=request.full_name,  # Set both for compatibility
        company_name=request.company_name,
        subscription_tier=SubscriptionTier.FREE,
        subscription_status="active",
        credits_balance=float(settings.FREE_CREDITS_ON_SIGNUP),
        is_active=True,
        is_verified=False
    )
    
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    
    logger.info(f"✅ User registered: {new_user.email} with {settings.FREE_CREDITS_ON_SIGNUP} free credits")
    
    # Create access token
    access_token = create_access_token(data={"sub": str(new_user.id)})
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=new_user.id,
            email=new_user.email,
            username=new_user.username,
            full_name=new_user.full_name,
            subscription_tier=new_user.subscription_tier.value,
            credits_balance=new_user.credits_balance
        )
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    response: Response = None,
    session: AsyncSession = Depends(get_async_session)
):
    """Login user and get JWT token"""
    
    # Find user by email (username field in OAuth2 form contains email)
    result = await session.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    
    # Update last login
    user.last_login = datetime.utcnow()
    await session.commit()
    
    logger.info(f"✅ User logged in: {user.email}")
    
    # Create access token
    access_token = create_access_token(data={"sub": str(user.id)})
    
    # Set cookie if response provided
    if response:
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            max_age=ACCESS_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            samesite="lax"
        )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=user.id,
            email=user.email,
            username=user.username,
            full_name=user.full_name or user.name,
            subscription_tier=user.subscription_tier.value,
            credits_balance=user.credits_balance
        )
    )


@router.post("/logout")
async def logout(response: Response):
    """Logout user (clear cookie)"""
    response.delete_cookie("access_token")
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current logged-in user info"""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        full_name=current_user.full_name or current_user.name,
        subscription_tier=current_user.subscription_tier.value,
        credits_balance=current_user.credits_balance
    )