from app.core.models import CampaignInput, Platform
from typing import Dict, Any, List
from pydantic import ValidationError
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InputValidator:
    def __init__(self):
        self.required_fields = ["product_name", "platforms", "daily_budget", "total_budget", "campaign_days"]

        # mapping common platform name variants -> canonical Platform.value
        self.platform_aliases = {
            "facebook": Platform.FACEBOOK,
            "fb": Platform.FACEBOOK,
            "instagram": Platform.INSTAGRAM,
            "insta": Platform.INSTAGRAM,
            "tiktok": Platform.TIKTOK,
            "tt": Platform.TIKTOK,
            "google": Platform.GOOGLE,
            "youtube": Platform.YOUTUBE,
            "yt": Platform.YOUTUBE,
            "linkedin": Platform.LINKEDIN,
            "linkedin.com": Platform.LINKEDIN,
            #"twitter": Platform.TWITTER,
            "x": Platform.X,
            "snapchat": Platform.SNAPCHAT,
        }

    def normalize_input(self, raw_input: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize input data (convert types, standardize formats)"""
        normalized = dict(raw_input)  # shallow copy

        # Ensure platforms are a list of canonical Platform enum values
        if "platforms" in normalized:
            platforms_raw = normalized["platforms"] or []
            normalized_platforms = []
            for p in platforms_raw:
                if not isinstance(p, str):
                    continue
                key = p.lower().strip()
                canonical = self.platform_aliases.get(key, key)
                # Convert to Platform enum if it's a valid platform
                try:
                    if isinstance(canonical, Platform):
                        normalized_platforms.append(canonical)
                    else:
                        # Try to convert string to Platform enum
                        platform_enum = Platform(canonical)
                        normalized_platforms.append(platform_enum)
                except ValueError:
                    # Skip invalid platforms
                    logger.warning(f"Skipping invalid platform: {p}")
                    continue
            normalized["platforms"] = normalized_platforms

        # Ensure target_location is list
        if "target_location" in normalized:
            if isinstance(normalized["target_location"], str):
                normalized["target_location"] = [
                    loc.strip() for loc in normalized["target_location"].split(",") if loc.strip()
                ]
            elif not isinstance(normalized["target_location"], list):
                normalized["target_location"] = []

        # Convert numeric fields to proper types
        if "daily_budget" in normalized:
            try:
                normalized["daily_budget"] = float(normalized["daily_budget"])
            except (TypeError, ValueError):
                raise ValueError("daily_budget must be a number")
        
        if "total_budget" in normalized:
            try:
                normalized["total_budget"] = float(normalized["total_budget"])
            except (TypeError, ValueError):
                raise ValueError("total_budget must be a number")
        
        if "campaign_days" in normalized:
            try:
                normalized["campaign_days"] = int(normalized["campaign_days"])
            except (TypeError, ValueError):
                raise ValueError("campaign_days must be an integer")

        # Basic trimming for strings
        for k, v in normalized.items():
            if isinstance(v, str):
                normalized[k] = v.strip()

        return normalized

    def validate_input(self, raw_input: Dict[str, Any]) -> CampaignInput:
        """Validate and parse raw user input into structured CampaignInput"""
        logger.info(f"Validating input for product: {raw_input.get('product_name', 'Unknown')}")
        
        # Basic required-field check first for quicker feedback
        missing_fields = [field for field in self.required_fields if field not in raw_input]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

        normalized = self.normalize_input(raw_input)

        try:
            # Use model_validate instead of parse_obj in Pydantic v2
            validated_input = CampaignInput.model_validate(normalized)
            logger.info("Input validation successful")
            return validated_input
        except ValidationError as e:
            # Format validation errors for better readability
            error_messages = []
            for error in e.errors():
                field = " -> ".join(str(loc) for loc in error['loc'])
                msg = error['msg']
                error_messages.append(f"{field}: {msg}")
            
            error_str = "; ".join(error_messages)
            logger.error(f"Input validation failed: {error_str}")
            raise ValueError(f"Input validation failed: {error_str}")

    def get_validation_rules(self) -> Dict[str, Any]:
        """Return validation rules for frontend guidance"""
        return {
            "required_fields": self.required_fields,
            "supported_platforms": [platform.value for platform in Platform],
            "platform_aliases": {k: v.value for k, v in self.platform_aliases.items()},
            "budget_constraints": {
                "daily_min": 1.0,
                "total_min": 10.0,
                "max_campaign_days": 365
            }
        }

    def validate_minimal_input(self, raw_input: Dict[str, Any]) -> bool:
        """Quick validation for minimal required fields only"""
        try:
            for field in self.required_fields:
                if field not in raw_input or not raw_input[field]:
                    return False
            return True
        except Exception:
            return False