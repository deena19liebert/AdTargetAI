# app/export_manager/google_ads_exporter.py
import os
import time
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime
from uuid import uuid4

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Try importing google-ads library; if not installed, real mode will error with clear message.
try:
    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
except Exception:
    GoogleAdsClient = None
    GoogleAdsException = None


class GoogleAdsExporter:
    """
    GoogleAdsExporter:
      - dry-run: builds payload and returns it so UI can preview (and returns mock exported IDs).
      - real-run: creates budget, campaign, ad group, and a responsive/ad (basic)
                using google-ads library and returns resource names/IDs.
    Environment variables required for real-run:
      - GOOGLE_ADS_DEVELOPER_TOKEN
      - GOOGLE_ADS_CLIENT_ID
      - GOOGLE_ADS_CLIENT_SECRET
      - GOOGLE_ADS_REFRESH_TOKEN
      - GOOGLE_ADS_LOGIN_CUSTOMER_ID (optional: manager account id)
      - GOOGLE_ADS_CUSTOMER_ID (target account numeric id, REQUIRED for real-run)
      - ALLOW_REAL_ADS = "true" to enable real mode on server
    NOTE: start with dry-run to verify payloads.
    """

    def __init__(self):
        
        logger.warning("GOOGLE ADS ENV CHECK → "
               f"DEV_TOKEN={bool(os.getenv('GOOGLE_ADS_DEVELOPER_TOKEN'))}, "
               f"CLIENT_ID={bool(os.getenv('GOOGLE_ADS_CLIENT_ID'))}, "
               f"CLIENT_SECRET={bool(os.getenv('GOOGLE_ADS_CLIENT_SECRET'))}, "
               f"REFRESH={bool(os.getenv('GOOGLE_ADS_REFRESH_TOKEN'))}, "
               f"CUSTOMER_ID={os.getenv('GOOGLE_ADS_CUSTOMER_ID')}")

        # required env vars (may be None for dry-run)
        self.developer_token = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN")
        self.client_id = os.getenv("GOOGLE_ADS_CLIENT_ID")
        self.client_secret = os.getenv("GOOGLE_ADS_CLIENT_SECRET")
        self.refresh_token = os.getenv("GOOGLE_ADS_REFRESH_TOKEN")
        self.login_customer_id = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID")  # manager account (optional)
        self.customer_id = os.getenv("GOOGLE_ADS_CUSTOMER_ID")  # target account, e.g. "1234567890"
        self.allow_real_ads = os.getenv("ALLOW_REAL_ADS", "false").lower() == "true"

        # google-ads client (created lazily)
        self.client = None
        if GoogleAdsClient is None:
            logger.warning("google-ads library not installed. Real exports will fail until installed.")
        else:
            # Build client config dict for in-memory init (don't rely on yaml file)
            if self.client_id and self.client_secret and self.refresh_token and self.developer_token:
                cfg = {
                    "developer_token": self.developer_token,
                    "use_proto_plus": True,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                }

                # login_customer_id should be provided as string without 'act_' prefix
                if self.login_customer_id:
                    cfg["login_customer_id"] = str(self.login_customer_id)
                try:
                    self.client = GoogleAdsClient.load_from_dict(cfg)
                    logger.info("GoogleAdsClient initialized successfully.")
                except Exception as e:
                    logger.warning("Failed to init GoogleAdsClient from env config: %s", e)

    # Public entrypoint - similar shape to your Facebook exporter
    def create_campaign_flow(self, campaign_data: Dict[str, Any], create_real_ads: bool = False) -> Dict[str, Any]:
        start_time = time.time()
        try:
            payload = self._build_payload(campaign_data)

            # DRY-RUN: include payload + mock exported ids so DB/UI is not null
            if not create_real_ads:
                mock_ids = self._generate_mock_ids()
                return {
                    "status": "success",
                    "platform": "google",
                    "mode": "dry_run",
                    "campaign_payload": payload,
                    "exported_ids": mock_ids,
                    "message": "Dry-run: google payload prepared.",
                    "execution_time": round(time.time() - start_time, 2),
                    "step_details": {
                        "budget": "payload generated",
                        "campaign": "payload generated",
                        "ad_group": "payload generated",
                        "ad": "payload generated",
                    },
                }

            # Real creation checks
            if not self.allow_real_ads:
                return {"status": "error", "platform": "google", "mode": "real", "message": "Server not configured to allow real ads. Set ALLOW_REAL_ADS=true", "execution_time": round(time.time() - start_time, 2)}

            if self.client is None:
                return {"status": "error", "platform": "google", "mode": "real", "message": "GoogleAdsClient not initialized. Check env vars and google-ads library.", "execution_time": round(time.time() - start_time, 2)}

            if not self.customer_id:
                return {"status": "error", "platform": "google", "mode": "real", "message": "GOOGLE_ADS_CUSTOMER_ID not set.", "execution_time": round(time.time() - start_time, 2)}

            # run creation (this is blocking — platform_router will run in a thread)
            creation_result = self._create_google_entities_sync(self.client, self.customer_id, payload)
            # if success and created keys exist, also produce exported_ids mapping for DB convenience
            if creation_result.get("status") == "success" and creation_result.get("created"):
                created = creation_result["created"]
                # resource names are strings (campaign_resource, ad_group_resource etc.)
                exported = {
                    "budget_resource": created.get("budget_resource"),
                    "campaign_resource": created.get("campaign_resource"),
                    "ad_group_resource": created.get("ad_group_resource"),
                    "ad_resource": created.get("ad_resource")
                }
                creation_result["exported_ids"] = exported

            creation_result["execution_time"] = round(time.time() - start_time, 2)
            return creation_result

        except Exception as e:
            logger.exception("Google create_campaign_flow failed: %s", e)
            return {"status": "error", "platform": "google", "message": str(e), "execution_time": round(time.time() - start_time, 2)}


    # Build logical payload (what we will send to Google). Keeps parity with FB exporter.
    def _build_payload(self, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        audience = campaign_data.get("audience_insights", {}) or {}
        campaign_input = campaign_data.get("campaign_input", {}) or {}

        name = campaign_input.get("product_name") or campaign_data.get("campaign_id") or f"GA_{uuid4().hex[:8]}"
        daily_budget = float(campaign_input.get("daily_budget") or 1.0)
        # convert to micros used by Google Ads (1 unit = 1e6 micros)
        budget_micros = int(daily_budget * 1_000_000)

        # simple targeting translation (countries)
        locations = audience.get("locations") or campaign_input.get("target_location") or ["US"]
        if isinstance(locations, str):
            locations = [locations]

        targeting = {
            "age_min": int(audience.get("age_min", 18)),
            "age_max": int(audience.get("age_max", 65)),
            "countries": locations,
            "interests": audience.get("interests", [])[:8],
            "languages": audience.get("languages", ["en"])[:3],
        }

        ad_copies = audience.get("ad_copies") or campaign_data.get("campaign_strategy", {}).get("ad_copies") or []
        if not isinstance(ad_copies, list):
            ad_copies = [ad_copies]

        # Build a single ad asset for demo (use responsive search/ad or expanded text equivalent)
        sample_ad = {
            "headline": (ad_copies[0].get("headline") if ad_copies else (campaign_input.get("product_name") or name))[:30],
            "description": (ad_copies[0].get("body") if ad_copies else (campaign_input.get("product_description", "") or ""))[:120],
            "final_url": campaign_input.get("landing_page") or campaign_input.get("product_url") or ""
        }

        payload = {
            "name": name,
            "daily_budget_micros": budget_micros,
            "targeting": targeting,
            "ad": sample_ad,
            "platform_meta": {
                "developer_token": bool(self.developer_token),
                "customer_id": self.customer_id
            }
        }
        return payload


    def health_check(self, customer_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Verifies Google Ads API connectivity using a safe read-only query.
        """
        try:
            if not self.client:
                return {
                    "status": "error",
                    "reason": "client_not_initialized",
                    "message": "GoogleAdsClient not initialized. Check env vars."
                }

            target_customer = customer_id or self.customer_id or self.login_customer_id
            if not target_customer:
                return {
                    "status": "error",
                    "reason": "missing_customer_id",
                    "message": "No customer ID available."
                }

            ga_service = self.client.get_service("GoogleAdsService")

            query = "SELECT customer.id, customer.descriptive_name FROM customer LIMIT 1"
            response = ga_service.search(
                customer_id=str(target_customer),
                query=query
            )

            rows = []
            for row in response:
                cust = row.customer
                rows.append({
                    "id": cust.id,
                    "descriptive_name": cust.descriptive_name
                })
                break

            return {
                "status": "ok",
                "rows": rows,
                "customer_id_used": target_customer
            }

        except GoogleAdsException as e:
            return {
                "status": "error",
                "reason": "google_ads_exception",
                "message": str(e)
            }
        except Exception as e:
            return {
                "status": "error",
                "reason": "exception",
                "message": str(e)
            }


    # Real-mode: create budget/campaign/adgroup/ad via google-ads client; returns resource_names
    def _create_google_entities_sync(self, client: "GoogleAdsClient", customer_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Steps:
          1) create campaign budget
          2) create campaign referencing budget
          3) create ad group referencing campaign
          4) create ad group ad (responsive search/ad)
        Returns created resource names keys: budget_resource, campaign_resource, ad_group_resource, ad_resource
        """
        results = {}
        step_details = {}
        errors = []

        try:
            # 1) create budget
            campaign_budget_service = client.get_service("CampaignBudgetService")
            budget_operation = client.get_type("CampaignBudgetOperation")
            budget = budget_operation.create
            budget.name = f"{payload['name']} Budget {int(time.time())}"
            budget.amount_micros = int(payload.get("daily_budget_micros", 1_000_000))
            budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD

            resp = campaign_budget_service.mutate_campaign_budgets(customer_id=customer_id, operations=[budget_operation])
            budget_resource = resp.results[0].resource_name
            results["budget_resource"] = budget_resource
            step_details["budget"] = f"Created budget {budget_resource}"
            logger.info("Created budget: %s", budget_resource)

            # 2) create campaign
            campaign_service = client.get_service("CampaignService")
            campaign_operation = client.get_type("CampaignOperation")
            campaign = campaign_operation.create
            campaign.name = payload["name"]
            # For demo, use SEARCH channel; change as needed to DISPLAY / VIDEO / PERFORMANCE_MAX
            campaign.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH
            campaign.manual_cpc.CopyFrom(client.get_type("ManualCpc"))  # simple bidding
            campaign.status = client.enums.CampaignStatusEnum.PAUSED
            campaign.campaign_budget = budget_resource

            resp = campaign_service.mutate_campaigns(customer_id=customer_id, operations=[campaign_operation])
            campaign_resource = resp.results[0].resource_name
            results["campaign_resource"] = campaign_resource
            step_details["campaign"] = f"Created campaign {campaign_resource}"
            logger.info("Created campaign: %s", campaign_resource)

            # 3) create ad group
            ad_group_service = client.get_service("AdGroupService")
            ad_group_operation = client.get_type("AdGroupOperation")
            ad_group = ad_group_operation.create
            ad_group.name = f"{payload['name']} AdGroup"
            ad_group.campaign = campaign_resource
            # set a simple CPC bid (in micros)
            ad_group.cpc_bid_micros = int(1000000)  # $1.00
            ad_group.status = client.enums.AdGroupStatusEnum.ENABLED

            resp = ad_group_service.mutate_ad_groups(customer_id=customer_id, operations=[ad_group_operation])
            ad_group_resource = resp.results[0].resource_name
            results["ad_group_resource"] = ad_group_resource
            step_details["ad_group"] = f"Created ad group {ad_group_resource}"
            logger.info("Created ad group: %s", ad_group_resource)

            # 4) create ad (Responsive Search Ad as safe default)
            ad_group_ad_service = client.get_service("AdGroupAdService")
            ad_group_ad_operation = client.get_type("AdGroupAdOperation")
            ad_group_ad = ad_group_ad_operation.create
            ad_group_ad.ad_group = ad_group_resource
            ad_group_ad.status = client.enums.AdGroupAdStatusEnum.PAUSED

            # Build the ad
            ad = ad_group_ad.ad
            # responsive_search_ad has headlines and descriptions arrays
            rsa = ad.responsive_search_ad
            # Use headline and description from payload['ad'] (repeat to reach min requirements)
            headline_text = payload["ad"].get("headline", payload["name"])[:30]
            desc_text = payload["ad"].get("description", "")[:90]
            # google requires 3 headlines and 2 descriptions; we'll create minimal variants
            def make_headline(h):
                ph = client.get_type("AdTextAsset")
                ph.text = str(h)[:30]
                return ph
            def make_desc(d):
                pd = client.get_type("AdTextAsset")
                pd.text = str(d)[:90]
                return pd

            rsa.headlines.extend([make_headline(headline_text), make_headline(headline_text + " - 2"), make_headline(headline_text + " - 3")])
            rsa.descriptions.extend([make_desc(desc_text), make_desc(desc_text + " - try now")])

            # final URL
            if payload["ad"].get("final_url"):
                ad.final_urls.append(payload["ad"]["final_url"])

            resp = ad_group_ad_service.mutate_ad_group_ads(customer_id=customer_id, operations=[ad_group_ad_operation])
            ad_resource = resp.results[0].resource_name
            results["ad_resource"] = ad_resource
            step_details["ad"] = f"Created ad {ad_resource}"
            logger.info("Created ad: %s", ad_resource)

            return {"status": "success", "platform": "google", "mode": "real", "created": results, "step_details": step_details}

        except GoogleAdsException as gae:
            logger.exception("GoogleAdsException: %s", gae)
            # parse errors for helpful messages
            errors = []
            for err in gae.failure.errors:
                errors.append({"message": err.message, "location": getattr(err, "location", None)})
            return {"status": "error", "platform": "google", "mode": "real", "message": str(gae), "errors": errors, "step_details": step_details}
        except Exception as e:
            logger.exception("Exception creating Google Ads objects: %s", e)
            return {"status": "error", "platform": "google", "mode": "real", "message": str(e), "step_details": step_details}


    def _generate_mock_ids(self) -> Dict[str, str]:
        """
        Generate realistic-looking mock IDs for dry-run mode (non-null).
        """
        ts = int(time.time())
        return {
            "campaign_resource": f"customers/{self.customer_id or '0000000000'}/campaigns/dry_{ts}",
            "ad_group_resource": f"customers/{self.customer_id or '0000000000'}/adGroups/dry_{ts}",
            "ad_resource": f"customers/{self.customer_id or '0000000000'}/adGroupAds/dry_{ts}",
            "budget_resource": f"customers/{self.customer_id or '0000000000'}/campaignBudgets/dry_{ts}",
        }
