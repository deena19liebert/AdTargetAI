from fastapi import FastAPI, HTTPException, Request, Header, APIRouter, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import shutil
import base64
import uvicorn
import os, json, logging
from datetime import datetime
import bcrypt
from typing import Optional, Dict, Any
from pathlib import Path
from dotenv import load_dotenv
import uuid
import asyncio
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

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CAMPAIGN_DIR = DATA_DIR / "campaigns"
DATA_DIR.mkdir(exist_ok=True)
CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)

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
    version="2.0.0",
    description="AI-Powered Marketing Campaign Generator with Mistral-7B",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

app.include_router(router, prefix="")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

campaigns_store: Dict[str, Any] = {}

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
# 🧠 BASIC ROUTES
# =====================================================


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serve the main web interface"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# =====================================================
# ✅ VALIDATION & INSIGHTS
# =====================================================

@app.post("/api/validate-input")
async def validate_input(raw_input: dict):
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
async def upload_image(request: Request, image: UploadFile = File(...)):
    """Handle image upload from the front-end.
    Saves file locally and returns absolute URL + (optional) image_hash.
    """

    try:
        # Validate file type
        if image.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
            return JSONResponse(
                status_code=400,
                content={"error": "Unsupported image type. Upload JPG or PNG only."},
            )

        # Secure unique filename
        ext = Path(image.filename).suffix or ".jpg"
        safe_name = f"{uuid.uuid4().hex}{ext}"
        save_path = UPLOAD_DIR / safe_name

        with save_path.open("wb") as buffer:
            shutil.copyfileobj(image.file, buffer)

        # Build accessible URL (relative)
        # request.base_url is like http://localhost:8000/
        upload_url = f"{request.base_url}uploads/{safe_name}"

        return {
            "url": upload_url,
            "path": f"/uploads/{safe_name}",
            "image_hash": None
        }

    except Exception as e:
        logger.exception("Image upload failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"error": f"Image upload failed: {str(e)}"},
        )
        
@app.post("/api/generate-insights")
async def generate_insights(raw_input: dict):
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


# =====================================================
# 🚀 MAIN CAMPAIGN GENERATOR
# =====================================================

@app.post("/api/generate-campaign")
async def generate_campaign(
    campaign_data: Dict[str, Any],
    session: AsyncSession = Depends(get_async_session)
):
    try:
        print(f"🚀 Generating campaign for: {campaign_data.get('product_name', 'Unknown')}")

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

        # 6️⃣ Save ROOT campaign into DB
        async with session.begin():

            # save campaign
            campaign = await create_campaign_and_store(
                session=session,
                campaign_slug=campaign_slug,
                product=validated_input.product_name,
                campaign_input=validated_input.dict(),
                audience_insights=audience_insights.dict(),
                campaign_strategy=campaign_strategy,
            )

            for platform_name, payload in platform_feeds.items():
                await create_platform_feed(
                    session=session,
                    campaign_slug_or_id=campaign.id,    
                    platform=platform_name,
                    payload=payload
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

        return {
            "status": "success",
            "campaign_id": campaign_slug,
            "data": complete_campaign,
            "message": "Campaign generated and stored in database"
        }

    except Exception as e:
        await session.rollback()
        print(f"❌ Campaign generation failed: {e}")
        raise HTTPException(status_code=400, detail=f"Campaign generation failed: {str(e)}")

# =====================================================
# 📦 CAMPAIGN MANAGEMENT
# =====================================================
@app.post("/api/reach-estimate")
async def reach_estimate(targeting: dict):
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
async def google_ads_health(session = Depends(get_async_session)):
    from app.export_manager.google_ads_exporter import GoogleAdsExporter
    exporter = GoogleAdsExporter()
    res = exporter.health_check()
    return res

@app.get("/api/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, session = Depends(get_async_session)):
    # memory -> disk -> DB fallback
    if campaign_id in campaigns_store:
        return campaigns_store[campaign_id]

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

    # convert to dict
    campaign_data = {
        "campaign_id": db_row.campaign_id,
        "product": db_row.product,
        "generated_at": db_row.generated_at.isoformat() if db_row.generated_at else None,
        "status": db_row.status,
        "campaign_input": db_row.campaign_input,
        "audience_insights": db_row.audience_insights,
        "campaign_strategy": db_row.campaign_strategy,
        "platform_feeds": getattr(db_row, "platform_feeds", None),
        "exported_ids": getattr(db_row, "exported_ids", None),
    }
    campaigns_store[campaign_id] = campaign_data
    return campaign_data


@app.get("/api/campaigns/{campaign_id}/download")
async def download_campaign(campaign_id: str, session = Depends(get_async_session)):
    # get campaign from memory/disk/DB then stream file
    data = await get_campaign(campaign_id, session)
    os.makedirs("exports", exist_ok=True)
    file_path = f"exports/{campaign_id}.json"
    with open(file_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, default=str)
    return FileResponse(path=file_path, filename=f"{campaign_id}_campaign.json", media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{campaign_id}_campaign.json"'})


@app.get("/api/campaigns")
async def list_campaigns(session = Depends(get_async_session)):
    # Return cached keys for now; full DB list can be added later
    return {"campaigns": list(campaigns_store.keys()), "count": len(campaigns_store)}


# -------------------------
# Export endpoint
# -------------------------
@router.post("/api/export-campaign/{campaign_id}")
async def export_campaign(
    campaign_id: str,
    export_request: Optional[Dict[str, Any]] = None,
    x_api_key: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_async_session),
):
    start_time = time.time()
    export_request = export_request or {}
    create_real_ads = bool(export_request.get("create_real_ads", False))

    # 1) load campaign from memory/disk/DB
    campaign_data = campaigns_store.get(campaign_id)
    if not campaign_data:
        disk_path = CAMPAIGN_DIR / f"{campaign_id}.json"
        if disk_path.exists():
            with open(disk_path, "r", encoding="utf-8") as fh:
                campaign_data = json.load(fh)
        else:
            db_row = await crud.get_campaign_by_campaign_id(session, campaign_id)
            if db_row:
                campaign_data = {
                    "campaign_id": db_row.campaign_id,
                    "product": db_row.product,
                    "campaign_input": db_row.campaign_input,
                    "audience_insights": db_row.audience_insights,
                    "campaign_strategy": db_row.campaign_strategy,
                    "platform_feeds": [pf for pf in (db_row.platform_feeds or [])],
                    "exported_ids": db_row.exported_ids,
                }

    if not campaign_data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # 2) determine platforms (robust)
    # campaign_data.platform_feeds might be list or dict; handle both
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
        results = await platform_router.export_to_platforms(campaign_data=campaign_data, platforms=platforms, create_real_ads=create_real_ads)
    except Exception as e:
        logger.exception("Platform router failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Platform router error: {str(e)}")

    # 5) Persist export metadata & logs (atomic-ish: commit once)
    db_row = await crud.get_campaign_by_campaign_id(session, campaign_id)
    aggregated_exported = db_row.exported_ids or {}
    try:
        # iterate each platform result and persist related rows / logs
        for platform_name, res in (results or {}).items():
            # create platform_feed row with payload
            try:
                pf_row = await crud.create_platform_feed(session, db_row.id, platform_name, payload=res.get("campaign_payload", {}))
            except Exception as e:
                logger.exception("Failed to create platform_feed row: %s", e)
                # continue - still try to persist other things
                pf_row = None

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
                try:
                    await crud.save_facebook_details(session, pf_row.id, fb_details)
                except Exception as e:
                    logger.exception("save_facebook_details failed: %s", e)

            # Log the export attempt
            try:
                await crud.log_export(session, pf_row.id if pf_row else None, "real" if create_real_ads else "dry_run",
                                      res.get("campaign_payload", {}), res, res.get("status") == "success",
                                      error=None if res.get("status") == "success" else res.get("message"))
            except Exception as e:
                logger.exception("log_export failed: %s", e)

            # update platform_feed export status (flush only)
            try:
                exported_ids = {k: res.get(k) for k in ("campaign_id","adset_id","creative_id","ad_id") if res.get(k)}
                await crud.update_platform_feed_export_status(session, pf_row.id if pf_row else None,
                                                              res.get("status", "pending"),
                                                              export_details=res,
                                                              exported_ids=exported_ids,
                                                              error_message=res.get("message"))
            except Exception as e:
                logger.exception("update_platform_feed_export_status failed: %s", e)

            # aggregate campaign-level exported ids if success
            if res.get("status") == "success":
                aggregated_exported[platform_name] = {k: res.get(k) for k in ("campaign_id","adset_id","creative_id","ad_id") if res.get(k)}
            else:
                # for dry-run, fill test ids if allowed by settings
                if not create_real_ads and getattr(settings, "ALLOW_PERSIST_TEST_EXPORTS", False):
                    aggregated_exported.setdefault(platform_name, {})
                    aggregated_exported[platform_name].update({
                        "campaign_id": res.get("campaign_id") or f"test_cid_{int(time.time())}",
                        "adset_id": res.get("adset_id") or f"test_asid_{int(time.time())}",
                        "creative_id": res.get("creative_id") or f"test_crid_{int(time.time())}",
                        "ad_id": res.get("ad_id") or f"test_adid_{int(time.time())}",
                    })

        # update campaign-level exported IDs + meta_status + export_history via crud helper
        await crud.update_exported_ids(session, db_row, aggregated_exported)

        # commit once
        await session.commit()

        # refresh in-memory cache
        campaign_data["exported_ids"] = aggregated_exported
        campaigns_store[campaign_id] = campaign_data

    except Exception as e:
        # try to rollback if something fatal occurred
        logger.exception("Failed to persist export metadata: %s", e)
        try:
            await session.rollback()
        except Exception:
            pass
        # non-fatal for responses - still return results
    execution_time = round(time.time() - start_time, 2)
    return {"status": "success", "campaign_id": campaign_id, "export_results": results, "message": f"Export attempted for {len(platforms)} platform(s)", "execution_time": execution_time}
# =====================================================
# 📚 PLATFORM INFO
# =====================================================
@router.get("/api/export-formats/{campaign_id}")
async def get_export_formats(campaign_id: str, session = Depends(get_async_session)):
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
