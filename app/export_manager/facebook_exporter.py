# app/export_manager/facebook_exporter.py
import os
import logging
import time
import json
from typing import Optional
from urllib.parse import urlencode
from datetime import datetime
from typing import Dict, Any, List, Optional

import requests
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.campaign import Campaign
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.adcreative import AdCreative
from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.targetingsearch import TargetingSearch

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class FacebookExporter:
    """
    FacebookExporter - handles dry-run payload generation and real campaign creation.
    Usage:
      fe = FacebookExporter()
      fe.create_campaign_flow(campaign_data, create_real_ads=False)  # dry-run
      fe.create_campaign_flow(campaign_data, create_real_ads=True)   # executes (requires valid token & permissions)
    """

    def __init__(self):
        self.ad_account_id = os.getenv("FACEBOOK_AD_ACCOUNT_ID")
        self.app_id = os.getenv("FACEBOOK_APP_ID")  # new: read app id
        self.app_secret = os.getenv("FACEBOOK_APP_SECRET")
        self.graph_version = os.getenv("FACEBOOK_GRAPH_VERSION", "v18.0")
        self.access_token = os.getenv("FACEBOOK_ACCESS_TOKEN")
        self.is_initialized = False
        self._initialize_facebook_api()

    def _initialize_facebook_api(self):
        """Initialize Facebook SDK if credentials present"""
        try:
            if not self.access_token:
                raise RuntimeError("FACEBOOK_ACCESS_TOKEN not found in environment")
            # Prefer explicit init with app_id, app_secret, access_token if app_id provided
            if self.app_id and self.app_secret and self.access_token:
                FacebookAdsApi.init(self.app_id, self.app_secret, self.access_token)
            else:
                # fallback: init using access_token only (works for some SDK setups)
                FacebookAdsApi.init(access_token=self.access_token, app_secret=self.app_secret)
            if not self.ad_account_id:
                logger.warning("FACEBOOK_AD_ACCOUNT_ID not set; real creation will fail without it")
            else:
                # normalize ad account id to start with act_
                if not str(self.ad_account_id).startswith("act_"):
                    self.ad_account_id = f"act_{self.ad_account_id}"
            self.is_initialized = True
            logger.info("Facebook SDK initialized.")
        except Exception as e:
            self.is_initialized = False
            logger.error("Facebook SDK init failed: %s", e)
        
        # Public entry
    def create_campaign_flow(self, campaign_data: Dict[str, Any], create_real_ads: bool = False) -> Dict[str, Any]:
        """
        Top-level: returns dry-run payload or executes real creation.
        campaign_data: final campaign object (like the one you store in campaigns_store)
        create_real_ads: when True, attempts to create campaign live using SDK
        """
        start_time = time.time()   # <-- FIX #1: define start_time

        try:
            # Build the Facebook-compatible payload 
            fb_payload = self._build_campaign_payload(campaign_data)

            # -----------------------------
            # DRY-RUN PATH (no real ads)
            # -----------------------------
            if not create_real_ads:

                # FIX #2: generate mock IDs so DB won't have NULL
                mock_ids = self._generate_mock_ids()

                return {
                    "status": "success",
                    "platform": "facebook",
                    "mode": "dry_run",
                    "campaign_payload": fb_payload,
                    "exported_ids": mock_ids,    # <-- FIX #3
                    "message": "Dry-run: payload prepared.",
                    "execution_time": round(time.time() - start_time, 2),
                    "step_details": {
                        "campaign": "Payload generated",
                        "adset": "Payload generated",
                        "creative": "Payload generated",
                        "ad": "Payload generated"
                    }
                }

            # -----------------------------
            # REAL RUN PATH (SDK execution)
            # -----------------------------
            if not self.is_initialized or not self.ad_account_id:
                return {
                    "status": "error",
                    "platform": "facebook",
                    "mode": "real",
                    "message": "Facebook SDK not initialized or FACEBOOK_AD_ACCOUNT_ID missing.",
                    "execution_time": round(time.time() - start_time, 2)
                }

            creation_result = self._create_facebook_entities_sync(fb_payload)
            creation_result["execution_time"] = round(time.time() - start_time, 2)
            return creation_result

        except Exception as e:
            logger.exception("create_campaign_flow failed: %s", e)
            return {
                "status": "error",
                "platform": "facebook",
                "message": str(e),
                "execution_time": round(time.time() - start_time, 2)
            }

    def _build_campaign_payload(self, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create the exact param dictionaries for:
        - campaign (POST /act_<id>/campaigns)
        - adset   (POST /act_<id>/adsets)
        - creative (POST /act_<id>/adcreatives)
        - ad      (POST /act_<id>/ads)
        """
        # Resolve page id
        page_id = os.getenv("FACEBOOK_PAGE_ID") or self._get_facebook_page_id()

        # Extract audience & interests
        audience = campaign_data.get("audience_insights", {}) or {}
        interests = audience.get("interests", []) or campaign_data.get("campaign_input", {}).get("interests", []) or []
        interest_objs = self._get_facebook_interest_ids(interests) if interests else []

        age_min = int(audience.get("age_min", 18))
        age_max = int(audience.get("age_max", 65))
        locations = audience.get("locations", campaign_data.get("campaign_input", {}).get("target_location", ["US"]))
        if isinstance(locations, str):
            locations = [locations]

        targeting = {
            "age_min": age_min,
            "age_max": age_max,
            "geo_locations": {"countries": locations},
        }
        if interest_objs:
            targeting["flexible_spec"] = [{"interests": [{"id": str(i["id"])} for i in interest_objs]}]

        # CTA mapping
        suggested_ctas = audience.get("suggested_ctas", []) or [campaign_data.get("campaign_input", {}).get("call_to_action", "Learn More")]
        cta_text = suggested_ctas[0] if suggested_ctas else "Learn More"
        cta_type = self._map_cta_to_facebook_type(cta_text)

        # budget -> cents
        daily_budget = campaign_data.get("campaign_input", {}).get("daily_budget", 1)
        try:
            daily_budget_cents = int(float(daily_budget) * 100)
        except Exception:
            daily_budget_cents = int(daily_budget)

        name = campaign_data.get("campaign_input", {}).get("product_name") or campaign_data.get("campaign_id") or f"Campaign {int(time.time())}"

        # Build object_story_spec (used by creative)
        object_story_spec = {
            "page_id": page_id,
            "link_data": {
                "message": campaign_data.get("campaign_input", {}).get("product_description", ""),
                "link": campaign_data.get("campaign_input", {}).get("product_url", "") or campaign_data.get("campaign_input", {}).get("landing_page", "") or ""
            }
        }

        # image handling (dry-run -> include image_url; real-run -> will replace with image_hash)
        image_url = (campaign_data.get("campaign_input", {}).get("image_url")
                    or campaign_data.get("campaign_input", {}).get("reference_image")
                    or None)
        if image_url:
            object_story_spec["link_data"]["image_url"] = image_url

        # creative params
        creative_params = {
            "name": f"{name} - Creative",
            "object_story_spec": object_story_spec,
        }

        # campaign params
        campaign_params = {
            "name": f"{name} - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "objective": campaign_data.get("campaign_strategy", {}).get("campaign_objective", "LINK_CLICKS") or "LINK_CLICKS",
            "status": "PAUSED",
            "special_ad_categories": [],
        }

        adset_params = {
            "name": f"{name} - AdSet",
            "daily_budget": daily_budget_cents,
            "campaign_id": "<CAMPAIGN_ID_PLACEHOLDER>",
            "billing_event": "IMPRESSIONS",
            "optimization_goal": "LINK_CLICKS",
            "targeting": targeting,
            "status": "PAUSED",
        }

        ad_params = {
            "name": f"{name} - Ad",
            "adset_id": "<ADSET_ID_PLACEHOLDER>",
            "creative": {"creative_id": "<CREATIVE_ID_PLACEHOLDER>"},
            "status": "PAUSED"
        }

        # If server configured for real ads and image_url is present -> upload to get image_hash
        if os.getenv("ALLOW_REAL_ADS", "false").lower() == "true" and image_url and self.ad_account_id and self.access_token:
            image_hash = self._upload_image_and_get_hash(image_url)
            if image_hash:
                # replace image_url with image_hash in object_story_spec and creative_params
                creative_params["object_story_spec"]["link_data"].pop("image_url", None)
                creative_params["object_story_spec"]["link_data"]["image_hash"] = image_hash

        # Attach tokens for dry-run debug views (safe)
        campaign_params["access_token"] = self.access_token
        adset_params["access_token"] = self.access_token
        creative_params["access_token"] = self.access_token
        ad_params["access_token"] = self.access_token

        return {
            "campaign": campaign_params,
            "adset": adset_params,
            "creative": creative_params,
            "ad": ad_params,
            "meta": {
                "ad_account": self.ad_account_id,
                "page_id": page_id,
                "interest_mapping": interest_objs,
                "cta_type": cta_type
            },
        }
        
    def _generate_mock_ids(self) -> Dict[str, str]:
        """
        Generate realistic-looking mock IDs for dry-run mode.
        These mimic Facebook's long numeric IDs but are clearly not real.
        """
        ts = int(time.time())
        return {
                "campaign_id": f"dry_fb_cmp_{ts}",
                "adset_id": f"dry_fb_set_{ts}",
                "creative_id": f"dry_fb_crt_{ts}",
                "ad_id": f"dry_fb_ad_{ts}",
        }



    def _create_facebook_entities_sync(self, fb_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Enhanced with step-by-step status tracking"""
        try:
            account = AdAccount(self.ad_account_id)
            created = {}
            step_details = {}
            errors = []

            # 1) Create Campaign
            try:
                campaign_params = dict(fb_payload["campaign"])
                campaign_params.pop("access_token", None)
                campaign_obj = account.create_campaign(params=campaign_params)
                campaign_id = self._extract_id_from_object(campaign_obj)
                if campaign_id:
                    created["campaign_id"] = campaign_id
                    step_details["campaign"] = f"Created successfully (ID: {campaign_id})"
                    logger.info("✅ Created Facebook Campaign: %s", campaign_id)
                else:
                    errors.append("Failed to create campaign: No ID returned")
                    step_details["campaign"] = "Failed - No ID returned"
            except Exception as e:
                error_msg = f"Campaign creation failed: {str(e)}"
                errors.append(error_msg)
                step_details["campaign"] = f"Failed - {str(e)}"
                raise Exception(error_msg)

            # 2) Create AdSet
            try:
                adset_params = dict(fb_payload["adset"])
                adset_params.pop("access_token", None)
                adset_params["campaign_id"] = created["campaign_id"]
                
                adset_obj = account.create_ad_set(params=adset_params)
                adset_id = self._extract_id_from_object(adset_obj)
                if adset_id:
                    created["adset_id"] = adset_id
                    step_details["adset"] = f"Created successfully (ID: {adset_id})"
                    logger.info("✅ Created Facebook AdSet: %s", adset_id)
                else:
                    errors.append("Failed to create adset: No ID returned")
                    step_details["adset"] = "Failed - No ID returned"
            except Exception as e:
                error_msg = f"AdSet creation failed: {str(e)}"
                errors.append(error_msg)
                step_details["adset"] = f"Failed - {str(e)}"
                raise Exception(error_msg)

            # 3) Create Creative
            try:
                creative_params = dict(fb_payload["creative"])
                creative_params.pop("access_token", None)
                
                creative_obj = account.create_ad_creative(params=creative_params)
                creative_id = self._extract_id_from_object(creative_obj)
                if creative_id:
                    created["creative_id"] = creative_id
                    step_details["creative"] = f"Created successfully (ID: {creative_id})"
                    logger.info("✅ Created Facebook Creative: %s", creative_id)
                else:
                    errors.append("Failed to create creative: No ID returned")
                    step_details["creative"] = "Failed - No ID returned"
            except Exception as e:
                error_msg = f"Creative creation failed: {str(e)}"
                errors.append(error_msg)
                step_details["creative"] = f"Failed - {str(e)}"
                raise Exception(error_msg)

            # 4) Create Ad
            try:
                ad_params = dict(fb_payload["ad"])
                ad_params.pop("access_token", None)
                ad_params["adset_id"] = created["adset_id"]
                ad_params["creative"] = {"creative_id": created["creative_id"]}
                
                ad_obj = account.create_ad(params=ad_params)
                ad_id = self._extract_id_from_object(ad_obj)
                if ad_id:
                    created["ad_id"] = ad_id
                    step_details["ad"] = f"Created successfully (ID: {ad_id})"
                    logger.info("✅ Created Facebook Ad: %s", ad_id)
                else:
                    errors.append("Failed to create ad: No ID returned")
                    step_details["ad"] = "Failed - No ID returned"
            except Exception as e:
                error_msg = f"Ad creation failed: {str(e)}"
                errors.append(error_msg)
                step_details["ad"] = f"Failed - {str(e)}"
                raise Exception(error_msg)

            if errors:
                return {
                    "status": "partial_success",
                    "platform": "facebook",
                    "mode": "real",
                    "created": created,
                    "step_details": step_details,
                    "errors": errors,
                    "message": f"Facebook campaign created with {len(errors)} error(s)"
                }
            else:
                return {
                    "status": "success",
                    "platform": "facebook",
                    "mode": "real",
                    "campaign_id": created["campaign_id"],
                    "adset_id": created["adset_id"],
                    "creative_id": created["creative_id"],
                    "ad_id": created["ad_id"],
                    "step_details": step_details,
                    "message": "Facebook campaign and all assets created successfully."
                }

        except Exception as e:
            logger.exception("Facebook creation flow failed: %s", e)
            return {
                "status": "error", 
                "platform": "facebook", 
                "message": str(e),
                "created": created,
                "step_details": step_details
            }

    # ---- Helpers for page & interests ----
    def _get_facebook_page_id(self) -> Optional[str]:
        """Try Graph API /me/accounts to find a page id for the token user."""
        try:
            url = f"https://graph.facebook.com/{self.graph_version}/me/accounts"
            params = {"access_token": self.access_token, "fields": "id,name"}
            resp = requests.get(url, params=params, timeout=8)
            data = resp.json()
            if isinstance(data, dict) and data.get("data"):
                logger.info("Auto-detected Facebook page: %s", data["data"][0].get("name"))
                return str(data["data"][0].get("id"))
        except Exception as e:
            logger.warning("Failed to auto-detect page id: %s", e)
        # fallback
        return os.getenv("FACEBOOK_PAGE_ID") or None

    def _search_facebook_interests(self, term: str) -> List[Dict[str, Any]]:
        """
        Use TargetingSearch (SDK) to find interest ids.
        Returns list of dicts {id, name} or [].
        """
        try:
            params = {"q": term, "type": "adinterest", "limit": 5}
            results = TargetingSearch.search(params=params)
            out = []
            for r in results:
                # r may behave like dict-like
                rid = r.get("id") if isinstance(r, dict) else r.get("id", None)
                rname = r.get("name") if isinstance(r, dict) else r.get("name", None)
                if rid:
                    out.append({"id": str(rid), "name": rname})
            return out
        except Exception as e:
            logger.warning("TargetingSearch failed for '%s': %s", term, e)
            # as fallback try HTTP Graph search
            try:
                url = f"https://graph.facebook.com/{self.graph_version}/search"
                resp = requests.get(url, params={"type": "adinterest", "q": term, "access_token": self.access_token}, timeout=8)
                data = resp.json()
                out = []
                for item in data.get("data", [])[:5]:
                    if "id" in item:
                        out.append({"id": str(item["id"]), "name": item.get("name")})
                return out
            except Exception as e2:
                logger.warning("HTTP interest search fallback failed: %s", e2)
                return []

    def _get_facebook_interest_ids(self, interests: List[str]) -> List[Dict[str, Any]]:
        """
        For each interest string, attempt to resolve to real FB interest object (id, name).
        Returns list of dicts.
        """
        resolved = []
        for interest in interests[:10]:  # limit to first 10 to be safe
            term = self._clean_interest_name(interest)
            hits = self._search_facebook_interests(term)
            if hits:
                resolved.append(hits[0])
                logger.info("Mapped interest '%s' -> %s", interest, hits[0].get("id"))
            else:
                logger.debug("No hit for interest '%s'", interest)
            time.sleep(0.2)
        if not resolved:
            # fallback static mapping
            resolved = self._get_fallback_interests()
        return resolved
    
    def _upload_image_and_get_hash(self, image_url: str) -> Optional[str]:
        """
        Upload an image to Facebook ad account and return image_hash.
        Required for real creatives — Facebook needs image_hash, not image_url.
        """
        if not image_url or not self.ad_account_id or not self.access_token:
            logger.warning("Image upload skipped — missing image_url or credentials.")
            return None

        url = f"https://graph.facebook.com/{self.graph_version}/{self.ad_account_id}/adimages"
        params = {
            "access_token": self.access_token,
            "url": image_url
        }

        try:
            resp = requests.post(url, data=params, timeout=20)
            data = resp.json()

            # Typical response:
            # {"images": {"image1.jpg": {"hash": "abc123hash"}}}
            images = data.get("images", {})
            if images:
                first = next(iter(images.values()))
                image_hash = first.get("hash")
                if image_hash:
                    logger.info(f"✅ Uploaded image → hash: {image_hash}")
                    return image_hash
            logger.warning(f"⚠️ No image hash returned. Response: {data}")
        except Exception as e:
            logger.error(f"❌ Image upload failed: {e}")

        return None


    def _clean_interest_name(self, interest: str) -> str:
        """Small heuristics to clean interest names for search"""
        if not interest:
            return ""
        s = interest.replace("_", " ").strip().lower()
        # remove short noise words
        noise = ["premium", "high end", "products", "enthusiast", "lovers", "tech"]
        for n in noise:
            s = s.replace(n, "")
        return s.strip()

    def _get_fallback_interests(self) -> List[Dict[str, Any]]:
        """Return a safe set of interest ids when lookup fails"""
        fallback = [
            {"id": "6003327766874", "name": "Wearable technology"},
            {"id": "6003320344664", "name": "Fitness"},
            {"id": "6003107902613", "name": "Luxury goods"},
        ]
        logger.warning("Using fallback interests: %s", [f["name"] for f in fallback])
        return fallback

    # ---- Mapping utilities ----
    def _map_cta_to_facebook_type(self, cta: str) -> str:
        if not cta:
            return "LEARN_MORE"
        c = cta.lower()
        mapping = {
            "shop now": "SHOP_NOW",
            "learn": "LEARN_MORE",
            "sign up": "SIGN_UP",
            "download": "DOWNLOAD",
            "book": "BOOK_TRAVEL",
            "get": "GET_OFFER",
        }
        for k, v in mapping.items():
            if k in c:
                return v
        return "LEARN_MORE"

    def _extract_id_from_object(self, obj: Any) -> Optional[str]:
        """
        Robust extraction of id from different SDK return shapes.
        SDK returns objects that may be dict-like or have get_id().
        """
        if obj is None:
            return None
        try:
            # dict-like
            if isinstance(obj, dict):
                return str(obj.get("id") or obj.get("campaign_id") or obj.get("adset_id") or obj.get("creative_id") or obj.get("ad_id"))
            # object with get_id()
            if hasattr(obj, "get_id") and callable(obj.get_id):
                return str(obj.get_id())
            # object with id key accessible like obj["id"]
            if hasattr(obj, "items"):
                return str(obj.get("id"))
        except Exception:
            pass
        # fallback: stringify
        try:
            as_str = str(obj)
            # sometimes the returned object is like {"id":"..."} string when printed
            return as_str
        except Exception:
            return None
