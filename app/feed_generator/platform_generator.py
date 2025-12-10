# app/feed_generator/platform_generator.py
"""
PlatformDataGenerator — strict Facebook API payload builder.
Returns an ordered list of actions (endpoint, method, params) that
mirror the Facebook Marketing API flow:
  1) POST /act_<AD_ACCOUNT_ID>/campaigns
  2) POST /act_<AD_ACCOUNT_ID>/adsets
  3) POST /act_<AD_ACCOUNT_ID>/adcreatives
  4) POST /act_<AD_ACCOUNT_ID>/ads

Each action is a dict:
  {
    "name": "create_campaign",
    "method": "POST",
    "endpoint": "https://graph.facebook.com/v18.0/act_<ID>/campaigns",
    "params": {...}
  }

This allows dry-run (show payloads) or real creation (execute in order).
"""
import os
import json
import time
import requests
from typing import List, Dict, Any

CACHE_FILE = os.path.join(os.getcwd(), "fb_interest_cache.json")


def _load_cache() -> Dict[str, Any]:
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache: Dict[str, Any]):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class PlatformDataGenerator:
    def __init__(self):
        self._cache = _load_cache()
        # default Graph version
        self.graph_version = os.getenv("FACEBOOK_GRAPH_VERSION", "v18.0")

    # public entrypoint used by main.py
    def generate_platform_feeds(self, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Returns dict keyed by platform. For facebook, returns
        {
          "actions": [ <ordered list of actions to POST> ],
          "dry_run": True/False,
        }
        """
        results = {}
        platforms = campaign_data.get("platforms", ["facebook"])
        for platform in platforms:
            if platform.lower() == "facebook":
                results["facebook"] = self._generate_facebook_actions(campaign_data)
            else:
                results[platform] = {"error": f"Platform '{platform}' not supported yet."}
        return results

    # ------------------------------
    # Facebook flow builder
    # ------------------------------
    def _generate_facebook_actions(self, campaign: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build strict API calls for Facebook campaign creation.
        Expects campaign to contain keys similar to your CampaignInput model.
        """
        access_token = os.getenv("FACEBOOK_ACCESS_TOKEN")
        if not access_token:
            return {"error": "FACEBOOK_ACCESS_TOKEN not set in environment variables."}

        ad_account = os.getenv("FACEBOOK_AD_ACCOUNT_ID")
        if not ad_account:
            return {"error": "FACEBOOK_AD_ACCOUNT_ID (act_...) not set."}
        # ensure prefix 'act_' is present — user should provide correct value
        if not str(ad_account).startswith("act_"):
            ad_account = f"act_{ad_account}"

        page_id = os.getenv("FACEBOOK_PAGE_ID")
        if not page_id:
            page_id = self._get_page_id_via_graph(access_token)

        # normalize incoming campaign fields
        name = campaign.get("product_name") or campaign.get("name") or f"Campaign {int(time.time())}"
        objective = (campaign.get("objective") or campaign.get("campaign_objective") or "LINK_CLICKS").upper()
        # Facebook objectives use specific enumerations; ensure uppercase
        daily_budget = campaign.get("daily_budget", campaign.get("budget_daily", 1000))
        # convert to smallest currency unit (e.g., cents)
        currency = os.getenv("FACEBOOK_CURRENCY", "USD").upper()
        try:
            # allow float or int; convert to integer smallest unit
            smallest_unit_budget = int(float(daily_budget) * 100)
        except Exception:
            smallest_unit_budget = int(daily_budget)

        start_time = campaign.get("start_time")
        end_time = campaign.get("end_time")

        # audiences/targeting
        audience = campaign.get("audience", {}) or {}
        if not audience:
            # fallback to earlier keys used in your example JSON
            audience = {
                "age_min": campaign.get("audience", {}).get("age_min", 18),
                "age_max": campaign.get("audience", {}).get("age_max", 65),
            }
        age_min = audience.get("age_min", 18)
        age_max = audience.get("age_max", 65)
        genders = audience.get("genders") or campaign.get("genders") or []
        locations = audience.get("locations") or campaign.get("target_location") or ["US"]
        if isinstance(locations, str):
            locations = [locations]

        interests = audience.get("interests") or campaign.get("interests") or []
        interest_ids = self._resolve_interest_ids(interests, access_token) if interests else []

        # target object per FB Marketing API
        targeting = {
            "geo_locations": {"countries": locations},
            "age_min": age_min,
            "age_max": age_max,
        }
        if genders:
            # Facebook expects integers 1 (male) or 2 (female); if strings present attempt mapping
            if all(isinstance(g, str) for g in genders):
                mapped = []
                for g in genders:
                    s = str(g).lower()
                    if s in ("male", "m"):
                        mapped.append(1)
                    elif s in ("female", "f"):
                        mapped.append(2)
                if mapped:
                    targeting["genders"] = mapped
            else:
                targeting["genders"] = genders
        if interest_ids:
            targeting["flexible_spec"] = [{"interests": [{"id": str(i)} for i in interest_ids]}]

        # creative spec
        creatives = campaign.get("creatives", {}) or {}
        message = creatives.get("message") or campaign.get("product_description", "")[:500]
        link = creatives.get("link") or campaign.get("landing_page") or campaign.get("reference_url") or "https://example.com"
        image_url = creatives.get("image_url")
        # When creating real ads you should upload image to /act_<id>/adimages and use image_hash.
        # For dry-run we keep image_url in link_data.

        # Build ordered actions
        base_url = f"https://graph.facebook.com/{self.graph_version}"
        actions = []

        # 1) Create Campaign
        actions.append({
            "name": "create_campaign",
            "method": "POST",
            "endpoint": f"{base_url}/{ad_account}/campaigns",
            "params": {
                "name": name,
                "objective": objective,
                "status": "PAUSED",
                "access_token": access_token
            }
        })

        # 2) Create AdSet (we attach to campaign via campaign_id later)
        adset_params = {
            "name": f"{name} - AdSet",
            "daily_budget": smallest_unit_budget,
            "billing_event": campaign.get("billing_event", "IMPRESSIONS"),
            "optimization_goal": campaign.get("optimization_goal", "LINK_CLICKS"),
            "targeting": json.dumps(targeting, ensure_ascii=False),
            "status": "PAUSED",
            "access_token": access_token
        }
        if start_time:
            adset_params["start_time"] = start_time
        if end_time:
            adset_params["end_time"] = end_time

        actions.append({
            "name": "create_adset",
            "method": "POST",
            "endpoint": f"{base_url}/{ad_account}/adsets",
            "params": adset_params
        })

        # 3) Create AdCreative (object_story_spec)
        object_story_spec = {"page_id": page_id, "link_data": {"message": message, "link": link}}
        if image_url:
            object_story_spec["link_data"]["image_url"] = image_url

        actions.append({
            "name": "create_adcreative",
            "method": "POST",
            "endpoint": f"{base_url}/{ad_account}/adcreatives",
            "params": {
                "name": f"{name} - Creative",
                "object_story_spec": json.dumps(object_story_spec, ensure_ascii=False),
                "access_token": access_token
            }
        })

        # 4) Create Ad (adset_id and creative_id will be inserted by executor after campaign/adset/creative created)
        actions.append({
            "name": "create_ad",
            "method": "POST",
            "endpoint": f"{base_url}/{ad_account}/ads",
            "params": {
                "name": f"{name} - Ad",
                # "adset_id": "<to_be_filled>",
                # "creative": json.dumps({"creative_id": "<to_be_filled>"}),
                "status": "PAUSED",
                "access_token": access_token
            },
            "requires": ["create_campaign", "create_adset", "create_adcreative"]  # metadata for executor
        })

        return {"actions": actions, "meta": {"ad_account": ad_account, "page_id": page_id, "currency": currency}}

    # ------------------------------
    # Helpers
    # ------------------------------
    def _get_page_id_via_graph(self, access_token: str) -> str:
        url = f"https://graph.facebook.com/{os.getenv('FACEBOOK_GRAPH_VERSION','v18.0')}/me/accounts"
        try:
            r = requests.get(url, params={"access_token": access_token, "fields": "id,name"}, timeout=8)
            data = r.json()
            if isinstance(data, dict) and "data" in data and data["data"]:
                desired_name = os.getenv("FACEBOOK_PAGE_NAME")
                if desired_name:
                    for p in data["data"]:
                        if p.get("name") == desired_name:
                            return str(p.get("id"))
                return str(data["data"][0].get("id"))
        except Exception as e:
            print("[WARN] _get_page_id_via_graph failed:", e)
        return None

    def _resolve_interest_ids(self, interests: List[str], access_token: str) -> List[str]:
        resolved = []
        cache_changed = False
        for term in interests:
            key = term.strip().lower()
            if not key:
                continue
            if key in self._cache:
                resolved.append(self._cache[key])
                continue
            # Graph API search for adinterest
            try:
                url = f"https://graph.facebook.com/{os.getenv('FACEBOOK_GRAPH_VERSION','v18.0')}/search"
                resp = requests.get(url, params={"type": "adinterest", "q": term, "limit": 5, "access_token": access_token}, timeout=8)
                data = resp.json()
                if isinstance(data, dict) and "data" in data and data["data"]:
                    first = data["data"][0]
                    if "id" in first:
                        self._cache[key] = str(first["id"])
                        resolved.append(str(first["id"]))
                        cache_changed = True
            except Exception as e:
                print(f"[WARN] Interest lookup failed for '{term}':", e)
            time.sleep(0.25)

        if cache_changed:
            _save_cache(self._cache)
        return resolved
