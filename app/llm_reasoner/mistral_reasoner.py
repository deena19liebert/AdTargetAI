# mistral_reasoner.py
import os
import json
import logging
import asyncio
import aiohttp
import regex as re
import time
import random
from typing import Dict, Any, List
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.models import CampaignInput, AudienceInsights
from app.core.config import settings

logger = logging.getLogger(__name__)


class MistralReasoner:
    def __init__(self):
        self.api_key = settings.MISTRAL_API_KEY
        self.base_url = "https://api.mistral.ai/v1"
        self.model = "mistral-large-latest"  # or "mistral-medium", "mistral-small"
        self.timeout = aiohttp.ClientTimeout(total=120)
        self.retry_attempts = 5  # Maximum retry attempts
        self.retry_delay = 2

        # Enhanced marketing intelligence
        self.marketing_knowledge = {
            "platform_strategies": {
                "facebook": "Broad targeting with detailed interests",
                "instagram": "Visual storytelling and influencer-style content",
                "tiktok": "Short-form viral videos with trending audio",
                "youtube": "Educational and review-style content",
                "linkedin": "Professional and B2B focused content",
                "x": "Real-time engagement and conversation",
                "snapchat": "Young audience with ephemeral content"
            }
        }

    def _save_raw_response(self, prefix: str, text: str) -> str:
        """Save raw LLM output for debugging; returns saved path or empty string on error."""
        try:
            out_dir = Path("exports/mistral_errors")
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            safe_prefix = re.sub(r'[^a-zA-Z0-9_-]', '_', prefix)[:40]
            path = out_dir / f"{safe_prefix}_{ts}.txt"
            path.write_text(text, encoding="utf-8", errors="ignore")
            logger.debug(f"Saved raw LLM output to: {path}")
            return str(path)
        except Exception as e:
            logger.warning(f"Failed to save raw LLM response: {e}")
            return ""

    async def infer_audience_insights(self, campaign_input: CampaignInput) -> AudienceInsights:
        """Generate audience insights with fallback handling"""
        logger.info(f"🎯 Generating AI insights for: {campaign_input.product_name}")

        max_retries = 2
        for attempt in range(max_retries):
            try:
                ai_insights = await self._generate_ai_insights(campaign_input)
                enhanced_insights = self._enhance_with_platform_strategies(ai_insights, campaign_input)
                return AudienceInsights.model_validate(enhanced_insights)

            except Exception as e:
                logger.warning(f"❌ AI insights attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    logger.warning("🔄 Using fallback insights generation")
                    fallback_insights = self._generate_fallback_insights(campaign_input)
                    return AudienceInsights.model_validate(fallback_insights)

                # Wait before retry
                await asyncio.sleep(2 ** attempt)  # Exponential backoff: 1, 2, ...

    async def _generate_ai_insights(self, campaign_input: CampaignInput) -> Dict[str, Any]:
        """Call Mistral API for intelligent audience analysis"""
        prompt = self._build_marketing_prompt(campaign_input)

        try:
            response = await self._call_mistral_api(prompt)
            insights = self._parse_ai_response(response)
            return insights

        except Exception as e:
            logger.error(f"Mistral API call failed: {e}")
            return self._generate_fallback_insights(campaign_input)

    def _build_marketing_prompt(self, campaign_input: CampaignInput) -> str:
        """Build a strict prompt that forces the model to return only JSON following an explicit schema."""
        platforms = [p.value for p in campaign_input.platforms]
        tz = getattr(campaign_input, "target_timezone", "UTC")

        return f"""You are an expert digital marketing analyst. GIVEN the product details below, produce a SINGLE valid JSON object ONLY (no explanation, no markdown, no code fences) that follows the exact schema and types shown.

PRODUCT:
name: {campaign_input.product_name}
description: {campaign_input.product_description}
category: {campaign_input.category}
price_range: {campaign_input.price_range}
platforms: {platforms}
locations: {campaign_input.target_location}
daily_budget: {campaign_input.daily_budget}
total_budget: {getattr(campaign_input, 'total_budget', None)}
campaign_days: {campaign_input.campaign_days}
call_to_action: {campaign_input.call_to_action}
timezone: {tz}

RETURN JSON SCHEMA (MUST match exactly):
{{
  "age_min":  integer,
  "age_max":  integer,
  "genders": ["female","male"],
  "interests": ["interest1","interest2","interest3"],
  "behaviors": ["behavior1","behavior2"],
  "locations": {json.dumps(campaign_input.target_location)},
  "languages": ["English"],
  "suggested_ctas": ["Shop Now","Learn More"],
  "campaign_objectives": ["awareness","conversions","engagement"],
  "hashtags": ["#tag1","#tag2"],
  "ad_copies": [
    {{"headline":"...", "body":"... (<=125 chars)","cta":"SHOP_NOW"}}
  ],
  "headlines": ["headline1","headline2"],
  "descriptions": ["short description"],
  "image_guidance": {{"aspect_ratio":"1.91:1","min_pixels":"600x315"}},
  "platform_recommendations": {{
    "facebook": "string",
    "instagram": "string",
    "tiktok": "string"
  }},
  "ideal_posting_times": {{
    "facebook": ["HH:MM","HH:MM"],
    "instagram": ["HH:MM"],
    "tiktok": ["HH:MM"]
  }},
  "posting_schedule": ["YYYY-MM-DDTHH:MM:SSZ or with timezone"],
  "platform_priority": ["facebook","instagram","tiktok"],
  "estimated_metrics": {{"ctr":"1.0-2.5%","cpc":"$0.30-$1.50","conversion_rate":"1-5%"}}
}}

GUIDELINES:
- Return ONLY the JSON object. No commentary.
- Use up to 8 relevant hashtags. Prefix with '#'.
- Provide 2-3 ad copy variants (headline <=40 chars, body <=125 chars).
- Post times must be in campaign timezone; posting_schedule should be ISO timestamps.
- Make ages consistent with price_range (e.g., premium -> older age_min).
- Keep outputs ASCII-safe and avoid special control characters.
"""

    async def _call_mistral_api(self, prompt: str) -> str:
        """Call Mistral API with robust retry/backoff and jitter. Returns raw assistant text content."""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,    # deterministic for strict JSON
            "max_tokens": 1600,
            "top_p": 1.0
        }

        for attempt in range(self.retry_attempts):
            try:
                async with aiohttp.ClientSession(timeout=self.timeout) as session:
                    async with session.post(url, headers=headers, json=payload) as response:
                        text = await response.text()
                        status = response.status

                        if status == 200:
                            # Prefer structured response content when available
                            try:
                                data = json.loads(text)
                                if isinstance(data, dict) and "choices" in data and data["choices"]:
                                    choice = data["choices"][0]
                                    # Mistral may place content in different shapes:
                                    if isinstance(choice.get("message"), dict) and "content" in choice["message"]:
                                        return choice["message"]["content"]
                                    if "text" in choice:
                                        return choice["text"]
                            except Exception:
                                # fallthrough to returning raw text
                                pass
                            return text

                        if status == 429:
                            # Rate-limited: attempt to use Retry-After header, otherwise exponential backoff with jitter
                            retry_after_header = response.headers.get("Retry-After")
                            try:
                                retry_after = int(retry_after_header) if retry_after_header is not None else None
                            except Exception:
                                retry_after = None

                            # compute fallback backoff: exponential with jitter
                            backoff = min(60, (2 ** attempt))  # 1,2,4,8,... capped at 60s
                            jitter = random.uniform(0.2, 1.0)
                            wait_time = (retry_after if retry_after is not None else backoff) + jitter

                            logger.warning(
                                "⚠️ Mistral API rate limit (429). attempt=%d/%d, retry_after_header=%r, backing off %.1fs",
                                attempt + 1, self.retry_attempts, retry_after_header, wait_time
                            )

                            if attempt < self.retry_attempts - 1:
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                # Last attempt, raise
                                raise Exception("Mistral API rate limit exceeded (429)")

                        # Non-429 error (4xx/5xx)
                        if status >= 400:
                            logger.error("❌ Mistral API returned status %s: %.300s", status, text)
                            if attempt < self.retry_attempts - 1:
                                # backoff before retrying non-429 transient errors
                                wait_time = min(60, (2 ** attempt)) + random.uniform(0.1, 0.8)
                                logger.info("🕒 Retrying after %.1fs (attempt %d/%d)...", wait_time, attempt + 1, self.retry_attempts)
                                await asyncio.sleep(wait_time)
                                continue
                            raise Exception(f"Mistral API error {status}: {text[:200]}")

                        # Fallback: unexpected branch — raise
                        logger.error("Unexpected response status from Mistral: %s", status)
                        raise Exception(f"Mistral API unexpected status {status}: {text[:200]}")

            except asyncio.TimeoutError:
                logger.warning("⏰ Mistral API timeout on attempt %d/%d", attempt + 1, self.retry_attempts)
                if attempt < self.retry_attempts - 1:
                    wait_time = min(60, (2 ** attempt)) + random.uniform(0.1, 0.6)
                    await asyncio.sleep(wait_time)
                    continue
                raise

            except Exception as e:
                # If it's clearly a rate limit error text returned somewhere else, handle as 429-like
                msg = str(e).lower()
                if ("rate limit" in msg or "429" in msg) and attempt < self.retry_attempts - 1:
                    wait_time = min(60, (2 ** attempt)) + random.uniform(0.2, 1.0)
                    logger.warning("⚠️ Mistral API call raised rate-limit-like error: %s. Backing off %.1fs", e, wait_time)
                    await asyncio.sleep(wait_time)
                    continue

                logger.warning("⚠️ Mistral API call failed (attempt %d/%d): %s", attempt + 1, self.retry_attempts, e)
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(min(60, (2 ** attempt)) + random.uniform(0.1, 0.6))
                    continue
                # re-raise the last error if final attempt
                raise

        # If we exit loop without returning
        raise Exception("All retry attempts to Mistral API failed")

    def _parse_ai_response(self, response_text: str) -> Dict[str, Any]:
        """Parse and validate AI response with robust error handling"""
        if not response_text:
            raise ValueError("Empty AI response")

        try:
            cleaned_text = self._clean_json_response(response_text)

            try:
                data = json.loads(cleaned_text)
            except json.JSONDecodeError as e:
                # try a second-pass heuristic cleanup (remove comments, convert single quotes, booleans, etc.)
                fallback_candidate = cleaned_text

                # Remove JS-style single-line and block comments
                fallback_candidate = re.sub(r'//.*?$', '', fallback_candidate, flags=re.MULTILINE)
                fallback_candidate = re.sub(r'/\*.*?\*/', '', fallback_candidate, flags=re.DOTALL)

                # Replace single quotes with double quotes (best-effort)
                # This is a heuristic and may not be perfect; used as a salvage step.
                fallback_candidate = fallback_candidate.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
                fallback_candidate = fallback_candidate.replace("'", '"')

                # Replace Python-style booleans/null to JSON
                fallback_candidate = re.sub(r'\bTrue\b', 'true', fallback_candidate)
                fallback_candidate = re.sub(r'\bFalse\b', 'false', fallback_candidate)
                fallback_candidate = re.sub(r'\bNone\b', 'null', fallback_candidate)

                # remove trailing commas again (defensive)
                fallback_candidate = re.sub(r',(\s*[}\]])', r'\1', fallback_candidate)

                try:
                    data = json.loads(fallback_candidate)
                    logger.warning("Parsed AI response using heuristic fallbacks (converted quotes/booleans/comments).")
                except Exception:
                    # Save raw for debugging and let caller fall back
                    path = self._save_raw_response("audience_insights_parse_error", response_text)
                    logger.warning(
                        "Failed to parse JSON from AI response after heuristics: %s (saved raw to %s)",
                        e,
                        path or "N/A",
                    )
                    raise ValueError("AI response contained invalid JSON") from e

            if "platform_recommendations" in data:
                for platform, recommendation in data["platform_recommendations"].items():
                    if isinstance(recommendation, dict):
                        data["platform_recommendations"][platform] = str(recommendation)
                    elif not isinstance(recommendation, str):
                        data["platform_recommendations"][platform] = str(recommendation)

            validated_data = self._validate_insights_data(data)
            return validated_data

        except ValueError:
            # Let caller handle fallback
            raise
        except Exception as e:
            # Truly unexpected errors
            path = self._save_raw_response("audience_insights_unexpected_error", response_text)
            logger.error(
                "Unexpected error parsing AI response: %s (saved raw to %s)",
                e,
                path or "N/A",
            )
            raise

    def _clean_json_response(self, text: str) -> str:
        """Clean and extract JSON from response text - more robust.

        - removes code fences
        - replaces smart quotes
        - strips non-printable control characters
        - removes JS comments (// and /* */)
        - finds outermost JSON object using regex for { ... }
        - removes trailing commas in objects/arrays (safe heuristic)
        """
        if not text:
            raise ValueError("Empty response text")

        # Quick sanitization
        t = text.replace("```json", "").replace("```", "")
        # replace smart quotes
        t = t.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
        # remove common non-printable control characters
        t = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', t)

        # Remove single-line JS style comments and block comments (best-effort)
        t = re.sub(r'//.*?$', '', t, flags=re.MULTILINE)
        t = re.sub(r'/\*.*?\*/', '', t, flags=re.DOTALL)

        # Attempt to extract the largest {...} block (supports nested with the `regex` module)
        matches = list(re.finditer(r'\{(?:[^{}]|(?R))*\}', t, re.DOTALL))
        if matches:
            # choose the longest match (most likely full JSON)
            longest = max(matches, key=lambda m: m.end() - m.start())
            candidate = longest.group(0)
        else:
            # fallback: try to extract content between first { and last }
            start = t.find('{')
            end = t.rfind('}')
            if start >= 0 and end > start:
                candidate = t[start:end+1]
            else:
                candidate = t

        # Heuristic: remove trailing commas before } or ]
        candidate = re.sub(r',(\s*[}\]])', r'\1', candidate)

        # Final safety: if non-ascii remains, encode-decode
        candidate = candidate.encode('utf-8', 'replace').decode('utf-8')

        # Save raw for debugging if candidate doesn't parse later (caller can call _save_raw_response)
        return candidate

    def _validate_insights_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize insights data (augmented)."""
        required_fields = {
            "age_min": 25,
            "age_max": 45,
            "genders": ["female", "male"],
            "interests": ["shopping", "lifestyle"],
            "behaviors": ["online_shopping"],
            "suggested_ctas": ["Shop Now"],
            "campaign_objectives": ["awareness", "conversions"],
            "platform_recommendations": {},
            "ideal_posting_times": {}
        }

        # Ensure required fields exist
        for field, default in required_fields.items():
            if field not in data or not data[field]:
                data[field] = default
                logger.warning(f"Missing field {field}, using default: {default}")

        # Age heuristic: coarsely adjust for price_range if present
        price = str(data.get("price_range", "")).lower() if "price_range" in data else ""
        # If price_range not present in data, try to use campaign_input (if caller saved it)
        if "price_range" in data:
            pr = data.get("price_range", "")
        else:
            pr = ""

        try:
            # Basic sanitization and bounds
            data["age_min"] = max(13, min(80, int(data["age_min"])))
            data["age_max"] = max(data["age_min"] + 1, min(80, int(data["age_max"])))
        except Exception:
            data["age_min"], data["age_max"] = required_fields["age_min"], required_fields["age_max"]

        # Heuristics by price_range if available on data
        if pr:
            p = pr.lower()
            if "luxury" in p:
                data["age_min"] = max(data["age_min"], 30)
            elif "premium" in p:
                data["age_min"] = max(data["age_min"], 25)
            elif "budget" in p:
                data["age_min"] = min(data["age_min"], 35)

        # Ensure lists properly formatted
        for field in ["genders", "interests", "behaviors", "suggested_ctas", "campaign_objectives"]:
            if not isinstance(data.get(field), list):
                data[field] = [str(data.get(field))] if data.get(field) is not None else []
            # strip and dedupe preserving order
            seen = set()
            normalized = []
            for item in data[field]:
                s = str(item).strip()
                if s and s not in seen:
                    normalized.append(s)
                    seen.add(s)
            data[field] = normalized

        # Normalize hashtags
        htags = data.get("hashtags", [])
        if not isinstance(htags, list):
            htags = [htags]
        normalized_hashtags = []
        for tag in htags[:8]:
            s = str(tag).strip()
            if not s:
                continue
            if not s.startswith("#"):
                s = "#" + s.replace(" ", "")
            normalized_hashtags.append(s)
        # dedupe preserving order
        data["hashtags"] = list(dict.fromkeys(normalized_hashtags))

        # Normalize ad_copies (list of dicts with headline/body/cta)
        ad_copies = data.get("ad_copies", [])
        normalized_ad_copies = []
        if isinstance(ad_copies, list):
            for ac in ad_copies[:5]:
                if isinstance(ac, dict):
                    headline = str(ac.get("headline", "")).strip()[:40]
                    body = str(ac.get("body", "")).strip()[:125]
                    cta = ac.get("cta") or (data.get("suggested_ctas") and data.get("suggested_ctas")[0]) or "LEARN_MORE"
                    normalized_ad_copies.append({"headline": headline, "body": body, "cta": cta})
                else:
                    # if string, treat as body
                    txt = str(ac).strip()
                    normalized_ad_copies.append({"headline": txt[:40], "body": txt[:125], "cta": data.get("suggested_ctas", ["LEARN_MORE"])[0]})
        data["ad_copies"] = normalized_ad_copies

        # Ensure platform_recommendations is dict and values are strings
        if not isinstance(data.get("platform_recommendations"), dict):
            data["platform_recommendations"] = {}
        else:
            for k, v in list(data["platform_recommendations"].items()):
                if not isinstance(v, str):
                    data["platform_recommendations"][k] = str(v)

        # ideal_posting_times: ensure format HH:MM and defaults
        defaults = {
            "facebook": ["19:00", "20:00"],
            "instagram": ["17:00", "19:00"],
            "tiktok": ["18:00", "20:00"]
        }
        ipt = data.get("ideal_posting_times") or {}
        if not isinstance(ipt, dict):
            ipt = {}
        for platform, times in defaults.items():
            if platform not in ipt or not ipt.get(platform):
                ipt[platform] = times
            else:
                # normalize times to HH:MM-ish (best-effort)
                normalized = []
                for t in ipt.get(platform, []):
                    s = str(t).strip()
                    m = re.match(r'^(\d{1,2}):(\d{2})$', s)
                    if m:
                        hh = int(m.group(1)) % 24
                        mm = int(m.group(2)) % 60
                        normalized.append(f"{hh:02d}:{mm:02d}")
                if not normalized:
                    ipt[platform] = times
                else:
                    ipt[platform] = normalized
        data["ideal_posting_times"] = ipt

        # posting_schedule: ensure list of ISO-like strings (best-effort)
        ps = data.get("posting_schedule", [])
        if not isinstance(ps, list):
            ps = [ps] if ps else []
        normalized_schedule = []
        iso_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(Z|[+\-]\d{2}:?\d{2})?$')
        for dt in ps[:10]:
            s = str(dt).strip()
            if iso_pattern.match(s):
                normalized_schedule.append(s)
            else:
                # try to accept YYYY-MM-DD HH:MM and convert to T + assume 'Z'
                m = re.match(r'^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(:\d{2})?$', s)
                if m:
                    normalized_schedule.append(f"{m.group(1)}T{m.group(2)}:00Z")
                else:
                    # keep original but short-circuit odd strings
                    if len(s) > 0:
                        normalized_schedule.append(s)
        data["posting_schedule"] = normalized_schedule

        return data

    def _enhance_with_platform_strategies(self, insights: Dict[str, Any], campaign_input: CampaignInput) -> Dict[str, Any]:
        """Enhance insights with platform-specific strategies"""

        platform_recs = insights.get("platform_recommendations", {})

        # Ensure all selected platforms have recommendations
        for platform in campaign_input.platforms:
            platform_key = platform.value
            if platform_key not in platform_recs:
                platform_recs[platform_key] = self._generate_platform_strategy(platform_key, campaign_input)

        insights["platform_recommendations"] = platform_recs

        # Ensure ideal posting times exist for major platforms
        posting_times = insights.get("ideal_posting_times", {})
        default_times = {
            "facebook": ["19:00", "20:00", "21:00"],
            "instagram": ["17:00", "19:00", "21:00"],
            "tiktok": ["18:00", "20:00", "22:00"],
            "youtube": ["20:00", "21:00", "22:00"]
        }

        for platform, times in default_times.items():
            if platform not in posting_times or not posting_times[platform]:
                posting_times[platform] = times

        insights["ideal_posting_times"] = posting_times

        return insights

    def _generate_platform_strategy(self, platform: str, campaign_input: CampaignInput) -> str:
        """Generate platform-specific strategy"""

        strategies = {
            "facebook": f"Use detailed interest targeting for {campaign_input.category} enthusiasts with carousel ads showcasing key benefits and social proof",
            "instagram": f"Leverage visual storytelling through Reels and Stories targeting {campaign_input.price_range} consumers interested in {campaign_input.category}",
            "tiktok": f"Create authentic, trending content with demonstrations and user testimonials targeting Gen Z and Millennials",
            "youtube": f"Produce educational content and detailed reviews targeting consideration-stage buyers researching {campaign_input.category}",
            "linkedin": f"Target professionals and B2B decision makers with case studies and industry insights about {campaign_input.category}",
            "x": f"Engage in real-time conversations about {campaign_input.category} using polls and thread storytelling for immediate engagement",
            "snapchat": f"Use AR filters and short, authentic video content targeting Gen Z with a sense of urgency and exclusivity"
        }

        return strategies.get(platform, f"Implement platform-appropriate content strategy focusing on {campaign_input.product_name} benefits")

    def _generate_fallback_insights(self, campaign_input: CampaignInput) -> Dict[str, Any]:
        """Generate fallback insights when AI fails"""

        logger.warning("Using fallback insights generation")

        # Price-based demographics
        price_range = campaign_input.price_range.lower()
        if "luxury" in price_range:
            age_range = [35, 65]
            interests = ["luxury_goods", "premium_brands", "exclusive_products", "quality_craftsmanship"]
            behaviors = ["affluent_shoppers", "brand_loyalty", "research_intensive"]
        elif "premium" in price_range:
            age_range = [28, 55]
            interests = ["quality_products", "brand_reputation", "premium_lifestyle", "durable_goods"]
            behaviors = ["comparison_shoppers", "review_readers", "value_seekers"]
        else:
            age_range = [18, 45]
            interests = ["value_shopping", "deals", "trendy_products", "budget_friendly"]
            behaviors = ["impulse_buyers", "social_shoppers", "deal_seekers"]

        # Add category-specific interests
        category = campaign_input.category.lower()
        if any(term in category for term in ['home', 'decor', 'furniture']):
            interests.extend(['home_improvement', 'interior_design', 'diy_projects'])
        elif any(term in category for term in ['tech', 'electronic', 'gadget']):
            interests.extend(['technology', 'innovation', 'gadget_reviews'])
        elif any(term in category for term in ['fitness', 'health', 'wellness']):
            interests.extend(['exercise', 'nutrition', 'healthy_lifestyle'])

        platforms = [p.value for p in campaign_input.platforms]
        platform_recs = {p: self._generate_platform_strategy(p, campaign_input) for p in platforms}

        return {
            "age_min": age_range[0],
            "age_max": age_range[1],
            "genders": ["female", "male"],
            "interests": list(set(interests)),  # Remove duplicates
            "behaviors": behaviors,
            "locations": campaign_input.target_location,
            "languages": ["English"],
            "suggested_ctas": [
                campaign_input.call_to_action,
                "Shop Now",
                "Discover More",
                "Get Started",
                "Learn More"
            ],
            "campaign_objectives": ["awareness", "conversions", "engagement"],
            "platform_recommendations": platform_recs,
            "ideal_posting_times": {
                "facebook": ["19:00", "20:00", "21:00"],
                "instagram": ["17:00", "19:00", "21:00"],
                "tiktok": ["18:00", "20:00", "22:00"],
                "youtube": ["20:00", "21:00", "22:00"]
            }
        }

    def _build_strategy_prompt(self, campaign_input: CampaignInput, audience_insights: AudienceInsights) -> str:
        """Generate the strict JSON-only strategy prompt used by generate_campaign_strategy."""
        platforms = [p.value for p in campaign_input.platforms]
        interests_preview = ", ".join(audience_insights.interests[:5]) if audience_insights.interests else "n/a"

        return f"""
As a senior marketing strategist, create a concise, data-driven campaign plan mapped directly to the provided audience insights.

PRODUCT: {campaign_input.product_name}
DESCRIPTION: {campaign_input.product_description}
CATEGORY: {campaign_input.category}
PRICE RANGE: {campaign_input.price_range}
TARGET AUDIENCE: {audience_insights.age_min}-{audience_insights.age_max} years old
INTERESTS: {interests_preview}
PLATFORMS: {platforms}
DAILY BUDGET: {campaign_input.daily_budget}
DURATION: {campaign_input.campaign_days} days

Return ONLY valid JSON with this exact structure, no text or markdown:

{{
    "targeting_strategy": {{
        "primary_audience": "string",
        "audience_size": "string",
        "targeting_approach": "string",
        "key_segments": ["segment1", "segment2"]
    }},
    "content_strategy": {{
        "key_messaging": ["msg1", "msg2"],
        "content_types": ["type1", "type2"],
        "visual_style": "string",
        "ad_copies": [
            {{"headline":"...", "body":"...", "cta":"SHOP_NOW"}}
        ]
    }},
    "budget_allocation": {{
        "platform_breakdown": {{"facebook": 35, "instagram": 25, "tiktok": 20, "youtube": 20}},
        "optimization_tips": ["Tip 1", "Tip 2"]
    }},
    "performance_predictions": {{
        "estimated_metrics": {{
            "ctr": "1.5-2.5%",
            "cpc": "$0.30-$1.50",
            "conversion_rate": "2-6%"
        }}
    }}
}}
"""

    async def generate_campaign_strategy(self, campaign_input: CampaignInput, audience_insights: AudienceInsights) -> Dict[str, Any]:
        """Generate complete campaign strategy using Mistral"""
        max_retries = 2
        last_error = None

        for attempt in range(max_retries):
            try:
                prompt = self._build_strategy_prompt(campaign_input, audience_insights)
                response = await self._call_mistral_api(prompt)
                strategy_data = json.loads(self._clean_json_response(response))
                return strategy_data

            except Exception as e:
                last_error = e
                logger.warning(f"❌ Strategy generation attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Wait before retry

        # If all retries fail, use fallback
        logger.error(f"🚨 All strategy generation attempts failed. Using fallback. Last error: {last_error}")
        return self._generate_fallback_strategy(campaign_input, audience_insights)

    def _generate_fallback_strategy(self, campaign_input: CampaignInput, audience_insights: AudienceInsights) -> Dict[str, Any]:
        """Generate fallback campaign strategy"""

        return {
            "targeting_strategy": {
                "primary_audience": f"{audience_insights.age_min}-{audience_insights.age_max} year olds interested in {', '.join(audience_insights.interests[:2])}",
                "audience_size": "50K-200K potential customers",
                "targeting_approach": "Interest-based targeting with demographic filters and lookalike audiences",
                "key_segments": audience_insights.interests[:3]
            },
            "content_strategy": {
                "key_messaging": [
                    f"Discover {campaign_input.product_name} - {campaign_input.product_description[:80]}...",
                    f"Perfect for people who love {', '.join(audience_insights.interests[:2])}",
                    "Join thousands of satisfied customers"
                ],
                "content_types": ["carousel_ads", "video_testimonials", "user_generated_content"],
                "visual_style": "Professional yet authentic with social proof elements"
            },
            "budget_allocation": {
                "platform_breakdown": {"facebook": 35, "instagram": 25, "tiktok": 20, "youtube": 20},
                "optimization_tips": [
                    "Start with 70% of budget for audience testing in first 3 days",
                    "Monitor CTR and conversion rates daily for quick optimization",
                    "Scale budget for audiences with CPA below $XX.XX after 3 days"
                ]
            },
            "performance_predictions": {
                "estimated_metrics": {
                    "ctr": "1.2-2.8%",
                    "cpc": f"${(campaign_input.daily_budget/1000):.2f}-${(campaign_input.daily_budget/500):.2f}",
                    "conversion_rate": "2-5%",
                    "roas": "180-350%"
                },
                "success_factors": [
                    "Compelling visual content that showcases product benefits",
                    "Clear value proposition in ad copy",
                    "Strong, action-oriented call-to-action"
                ]
            }
        }
