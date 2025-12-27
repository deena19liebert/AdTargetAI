# app/crud.py
from typing import Dict, Any, Optional
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError

# import your ORM models (make sure these files exist and are correct)
from app.db.models.campaign import Campaign
from app.db.models.platform_feed import PlatformFeed
from app.db.models.facebook_details import FacebookDetails
from app.db.models.export_log import ExportLog
from app.db.models.uploaded_image import UploadedImage

# -------------------------------
# Create a campaign (root record)
# -------------------------------
async def create_campaign_and_store(
    session: AsyncSession,
    campaign_slug: str,
    product: str,
    campaign_input: Dict[str, Any],
    audience_insights: Dict[str, Any],
    campaign_strategy: Dict[str, Any],
) -> Campaign:
    """
    Creates a Campaign row and flushes to make .id available.
    Returns the Campaign instance (detached but with id populated).
    """
    try:
        campaign = Campaign(
            campaign_id=campaign_slug,
            product=product,
            product_description=campaign_input.get("product_description") or campaign_input.get("product_name"),
            campaign_input=campaign_input,
            audience_insights=audience_insights,
            campaign_strategy=campaign_strategy,
            status="ready",
        )
        session.add(campaign)
        await session.flush()
        await session.refresh(campaign)
        return campaign
    except SQLAlchemyError as e:
        await session.rollback()
        raise Exception(f"Failed to create campaign: {str(e)}")


# -------------------------------
# Create a platform feed row
# -------------------------------
async def create_platform_feed(
    session: AsyncSession,
    campaign_slug_or_id,
    platform: str,
    payload: Dict[str, Any],
) -> PlatformFeed:
    """Create platform feed with provisional ID"""
    try:
        campaign_id = None

        if isinstance(campaign_slug_or_id, int):
            campaign_id = campaign_slug_or_id
        else:
            q = select(Campaign).where(Campaign.campaign_id == str(campaign_slug_or_id))
            res = await session.execute(q)
            campaign_row = res.scalar_one_or_none()
            if not campaign_row:
                raise ValueError(f"Campaign not found for campaign_slug: {campaign_slug_or_id}")
            campaign_id = campaign_row.id

        provisional_id = f"{platform}_{uuid.uuid4().hex[:8]}"

        pf = PlatformFeed(
            campaign_id=campaign_id,
            platform=platform,
            feed_data=payload,
            provisional_id=provisional_id,
            status="created"
        )

        session.add(pf)
        await session.flush()
        await session.refresh(pf)
        return pf
    except SQLAlchemyError as e:
        await session.rollback()
        raise Exception(f"Failed to create platform feed: {str(e)}")
    
# -------------------------------
# Facebook details saver
# -------------------------------
async def save_facebook_details(session: AsyncSession, platform_feed_id, details: Dict[str, Any]):
    fb = FacebookDetails(
        platform_feed_id=platform_feed_id,
        ad_account=details.get("ad_account"),
        page_id=details.get("page_id"),
        targeting=details.get("targeting"),
        creative=details.get("creative"),
        budget_cents=details.get("budget_cents"),
        scheduling=details.get("scheduling"),
        exported_ids=details.get("exported_ids"),
    )
    session.add(fb)
    await session.flush()
    return fb

# -------------------------------
# Export logging
# -------------------------------
async def log_export(session: AsyncSession, platform_feed_id, mode: str, request_payload: Dict[str, Any], response: Dict[str, Any], success: bool, error: Optional[str] = None):
    log = ExportLog(
        platform_feed_id=platform_feed_id,
        mode=mode,
        success=success,
        request_payload=request_payload,
        response=response,
        error=error,
    )
    session.add(log)
    await session.flush()
    return log

# -------------------------------
# Uploaded image saver
# -------------------------------
async def save_uploaded_image(session: AsyncSession, filename: str, path: str, url: str, mime: str, metadata: Dict[str, Any]):
    img = UploadedImage(
        filename=filename,
        path=path,
        url=url,
        mime=mime,
        extra_metadata=metadata if metadata is not None else {},
    )
    session.add(img)
    await session.flush()
    return img

async def get_campaign_by_campaign_id(session: AsyncSession, campaign_slug: str) -> Optional[Campaign]:
    if isinstance(campaign_slug, uuid.UUID):
        campaign_slug = str(campaign_slug)
    q = select(Campaign).where(Campaign.campaign_id == str(campaign_slug)).options(selectinload(Campaign.platform_feeds))
    res = await session.execute(q)
    return res.scalar_one_or_none()

async def update_exported_ids(session: AsyncSession, campaign_row: Campaign, exported_ids: Dict[str, Any]):
    """
    Persist exported ids on related facebook_details or campaign table depending on your schema.
    This example assumes campaign_row has exported_ids column (JSON). If you store per-platform, adapt.
    """
    # If Campaign has an exported_ids JSON column:
    if hasattr(campaign_row, "exported_ids"):
        campaign_row.exported_ids = exported_ids
        session.add(campaign_row)
        await session.flush()
        return campaign_row

    # Otherwise, find the PlatformFeed -> FacebookDetails and update that row.
    # (Implementation depends on your models.)
    return None

# Add these enhanced CRUD operations

async def update_exported_ids(session: AsyncSession, campaign_row: Campaign, exported_ids: Dict[str, Any]):
    """
    Persist exported ids at campaign level, update meta_status, export_history and last_export_attempt.
    Important: do NOT commit inside this function; let caller commit.
    """
    try:
        if not campaign_row:
            raise ValueError("campaign_row is None")

        # Ensure exported_ids is a dict on the row
        existing = campaign_row.exported_ids or {}
        existing.update(exported_ids or {})
        campaign_row.exported_ids = existing

        # meta_status: basic last export info
        ms = campaign_row.meta_status or {}
        ms["last_export"] = {
            "ts": datetime.utcnow().isoformat(),
            "platforms": list((exported_ids or {}).keys()),
            "summary": {k: v for k, v in (exported_ids or {}).items()}
        }
        campaign_row.meta_status = ms

        # export_history: append an entry
        hist = campaign_row.export_history or []
        hist.append({
            "ts": datetime.utcnow().isoformat(),
            "exported_ids": exported_ids or {},
        })
        campaign_row.export_history = hist

        # last_export_attempt
        campaign_row.last_export_attempt = datetime.utcnow()

        session.add(campaign_row)
        await session.flush()
        return campaign_row

    except SQLAlchemyError as e:
        await session.rollback()
        raise Exception(f"Failed to update exported_ids/meta_status: {str(e)}")

async def update_campaign_export_status(
    session: AsyncSession,
    campaign_id: int,
    platform: str,
    export_result: Dict[str, Any]
):
    """Update campaign with platform-specific export status"""
    campaign = await get_campaign_by_id(session, campaign_id)
    if not campaign:
        return None

    # Initialize meta_status if not exists
    if not campaign.meta_status:
        campaign.meta_status = {}
    
    # Update platform status
    campaign.meta_status[platform] = {
        "status": export_result.get("status"),
        "last_attempt": datetime.now().isoformat(),
        "execution_time": export_result.get("execution_time"),
        "step_details": export_result.get("step_details", {}),
        "errors": export_result.get("errors", [])
    }
    
    # Update exported_ids
    if export_result.get("status") == "success" and not campaign.exported_ids:
        campaign.exported_ids = {}
    
    if platform == "facebook" and export_result.get("status") == "success":
        campaign.exported_ids[platform] = {
            "campaign_id": export_result.get("campaign_id"),
            "adset_id": export_result.get("adset_id"),
            "creative_id": export_result.get("creative_id"),
            "ad_id": export_result.get("ad_id")
        }
    
    campaign.last_export_attempt = func.now()
    await session.commit()
    return campaign

async def get_campaign_by_id(session: AsyncSession, campaign_id: int) -> Optional[Campaign]:
    """Get campaign by internal ID (not campaign_id slug)"""
    q = select(Campaign).where(Campaign.id == campaign_id).options(selectinload(Campaign.platform_feeds))
    res = await session.execute(q)
    return res.scalar_one_or_none()

async def get_campaign_export_status(session: AsyncSession, campaign_slug: str) -> Dict[str, Any]:
    """Get comprehensive export status for a campaign"""
    campaign = await get_campaign_by_campaign_id(session, campaign_slug)
    if not campaign:
        return {"error": "Campaign not found"}
    
    status_info = {
        "campaign_id": campaign.campaign_id,
        "overall_status": campaign.status,
        "platforms": {},
        "export_history": campaign.export_history or [],
        "last_export_attempt": campaign.last_export_attempt.isoformat() if campaign.last_export_attempt else None
    }
    
    for feed in campaign.platform_feeds:
        status_info["platforms"][feed.platform] = {
            "feed_status": feed.status,
            "export_status": feed.export_status,
            "last_attempt": feed.last_export_attempt.isoformat() if feed.last_export_attempt else None,
            "exported_ids": feed.exported_ids,
            "error_message": feed.error_message
        }
    
    return status_info

async def update_platform_feed_export_status(
    session: AsyncSession,
    platform_feed_id: int,
    status: str,
    export_details: Dict[str, Any],
    exported_ids: Dict[str, Any],
    error_message: Optional[str] = None
):
    """Update platform feed export status after export attempt"""
    try:
        stmt = (
            update(PlatformFeed)
            .where(PlatformFeed.id == platform_feed_id)
            .values(
                export_status=status,
                export_details=export_details,
                exported_ids=exported_ids,
                last_export_attempt=datetime.utcnow(),
                error_message=error_message
            )
        )
        await session.execute(stmt)
        await session.flush()
        
    except SQLAlchemyError as e:
        logger.error(f"Failed to update platform feed status: {e}")
        raise Exception(f"Failed to update export status: {str(e)}")