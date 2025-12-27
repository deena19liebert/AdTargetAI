# app/crud_user.py
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from datetime import datetime

from app.db.models.user import User
from app.db.models.transaction import Transaction, TransactionType, TransactionStatus
from app.db.models.credit_usage import CreditUsage
from app.auth.security import get_password_hash, verify_password

# =====================================================
# USER CRUD
# =====================================================

async def create_user(
    session: AsyncSession,
    email: str,
    password: str,
    username: Optional[str] = None,
    full_name: Optional[str] = None,
    company_name: Optional[str] = None,
    initial_credits: float = 0.0
) -> User:
    """Create a new user"""
    try:
        user = User(
            email=email.lower().strip(),
            username=username,
            password_hash=get_password_hash(password),
            full_name=full_name,
            company_name=company_name,
            credits_balance=initial_credits,
            is_active=True,
            is_verified=False
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user
    except IntegrityError as e:
        await session.rollback()
        if "email" in str(e.orig):
            raise ValueError("Email already registered")
        elif "username" in str(e.orig):
            raise ValueError("Username already taken")
        raise ValueError("User creation failed")

async def get_user_by_email(session: AsyncSession, email: str) -> Optional[User]:
    """Get user by email"""
    query = select(User).where(User.email == email.lower().strip())
    result = await session.execute(query)
    return result.scalar_one_or_none()

async def get_user_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
    """Get user by ID"""
    query = select(User).where(User.id == user_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()

async def get_user_by_username(session: AsyncSession, username: str) -> Optional[User]:
    """Get user by username"""
    query = select(User).where(User.username == username.strip())
    result = await session.execute(query)
    return result.scalar_one_or_none()

async def authenticate_user(session: AsyncSession, email: str, password: str) -> Optional[User]:
    """Authenticate user with email and password"""
    user = await get_user_by_email(session, email)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user

async def update_user_credits(
    session: AsyncSession,
    user: User,
    credits_to_add: float
) -> User:
    """Add credits to user account"""
    user.add_credits(credits_to_add)
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user

async def update_last_login(session: AsyncSession, user: User):
    """Update user's last login timestamp"""
    user.last_login = datetime.utcnow()
    session.add(user)
    await session.flush()

# =====================================================
# TRANSACTION CRUD
# =====================================================

async def create_transaction(
    session: AsyncSession,
    user_id: int,
    amount_inr: float,
    credits_purchased: float,
    transaction_type: TransactionType = TransactionType.CREDIT_PURCHASE,
    razorpay_order_id: Optional[str] = None,
    description: Optional[str] = None
) -> Transaction:
    """Create a new transaction record"""
    transaction = Transaction(
        user_id=user_id,
        transaction_type=transaction_type,
        status=TransactionStatus.PENDING,
        amount_inr=amount_inr,
        credits_purchased=credits_purchased,
        razorpay_order_id=razorpay_order_id,
        description=description
    )
    session.add(transaction)
    await session.flush()
    await session.refresh(transaction)
    return transaction

async def update_transaction_status(
    session: AsyncSession,
    transaction_id: int,
    status: TransactionStatus,
    razorpay_payment_id: Optional[str] = None,
    razorpay_signature: Optional[str] = None,
    payment_method: Optional[str] = None,
    failure_reason: Optional[str] = None
) -> Transaction:
    """Update transaction status"""
    query = select(Transaction).where(Transaction.id == transaction_id)
    result = await session.execute(query)
    transaction = result.scalar_one_or_none()
    
    if not transaction:
        raise ValueError("Transaction not found")
    
    transaction.status = status
    if razorpay_payment_id:
        transaction.razorpay_payment_id = razorpay_payment_id
    if razorpay_signature:
        transaction.razorpay_signature = razorpay_signature
    if payment_method:
        transaction.payment_method = payment_method
    if failure_reason:
        transaction.failure_reason = failure_reason
    
    if status == TransactionStatus.SUCCESS:
        transaction.completed_at = datetime.utcnow()
    
    session.add(transaction)
    await session.flush()
    await session.refresh(transaction)
    return transaction

async def get_user_transactions(
    session: AsyncSession,
    user_id: int,
    limit: int = 50
) -> List[Transaction]:
    """Get user's transaction history"""
    query = (
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(query)
    return result.scalars().all()

# =====================================================
# CREDIT USAGE CRUD
# =====================================================

async def record_credit_usage(
    session: AsyncSession,
    user: User,
    credits_used: float,
    action: str,
    campaign_id: Optional[int] = None,
    details: Optional[dict] = None
) -> CreditUsage:
    """Record credit usage and deduct from user balance"""
    balance_before = user.credits_balance
    
    # Deduct credits from user
    user.deduct_credits(credits_used)
    session.add(user)
    await session.flush()
    
    balance_after = user.credits_balance
    
    # Create usage record
    usage = CreditUsage(
        user_id=user.id,
        campaign_id=campaign_id,
        credits_used=credits_used,
        action=action,
        details=details,
        balance_before=balance_before,
        balance_after=balance_after
    )
    session.add(usage)
    await session.flush()
    await session.refresh(usage)
    return usage

async def get_user_credit_usage_history(
    session: AsyncSession,
    user_id: int,
    limit: int = 50
) -> List[CreditUsage]:
    """Get user's credit usage history"""
    query = (
        select(CreditUsage)
        .where(CreditUsage.user_id == user_id)
        .order_by(CreditUsage.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(query)
    return result.scalars().all()

async def get_user_total_credits_used(session: AsyncSession, user_id: int) -> float:
    """Get total credits used by user"""
    query = select(func.sum(CreditUsage.credits_used)).where(CreditUsage.user_id == user_id)
    result = await session.execute(query)
    total = result.scalar()
    return total if total else 0.0