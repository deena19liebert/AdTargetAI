# app/export_manager/platform_router.py
import logging
import asyncio
import inspect
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class PlatformRouter:
    def __init__(self):
        self.timeout = 30

    async def _call_exporter(self, exporter_obj, campaign_data: Dict[str, Any], create_real_ads: bool = False) -> Dict[str, Any]:
        """
        Call exporter.create_campaign_flow in a safe way:
          - If exporter.create_campaign_flow is async -> await it
          - If it's sync -> run in thread via asyncio.to_thread
        """
        fn = getattr(exporter_obj, "create_campaign_flow", None)
        if fn is None:
            raise AttributeError("Exporter missing create_campaign_flow method")

        if inspect.iscoroutinefunction(fn):
            return await fn(campaign_data, create_real_ads)
        else:
            # run synchronous work in thread to avoid blocking event loop
            return await asyncio.to_thread(fn, campaign_data, create_real_ads)

    async def export_to_platforms(self, campaign_data: Dict[str, Any], platforms: List[str], create_real_ads: bool = False) -> Dict[str, Any]:
        """Export campaign to multiple platforms concurrently."""
        if not isinstance(platforms, list):
            raise ValueError("platforms must be a list of platform keys (e.g. ['facebook','google'])")

        tasks = []
        platform_map = {}  # platform -> task index
        for platform in platforms:
            platform_lower = str(platform).lower()
            try:
                if platform_lower == "facebook":
                    from app.export_manager.facebook_exporter import FacebookExporter
                    exporter = FacebookExporter()
                elif platform_lower == "google":
                    from app.export_manager.google_ads_exporter import GoogleAdsExporter
                    exporter = GoogleAdsExporter()
                elif platform_lower == "tiktok":
                    from app.export_manager.tiktok_exporter import TikTokExporter
                    exporter = TikTokExporter()
                elif platform_lower == "instagram":
                    from app.export_manager.instagram_exporter import InstagramExporter
                    exporter = InstagramExporter()
                elif platform_lower == "linkedin":
                    from app.export_manager.linkedin_exporter import LinkedInExporter
                    exporter = LinkedInExporter()
                else:
                    # Not implemented
                    logger.info("Platform '%s' not implemented - skipping", platform_lower)
                    tasks.append(asyncio.sleep(0, result={"status": "skipped", "platform": platform_lower, "message": f"Platform {platform_lower} not implemented"}))
                    platform_map[platform_lower] = len(tasks) - 1
                    continue

                # schedule exporter call
                task = asyncio.create_task(self._call_exporter(exporter, campaign_data, create_real_ads))
                tasks.append(task)
                platform_map[platform_lower] = len(tasks) - 1

            except Exception as e:
                logger.exception("Failed to initialize exporter for %s: %s", platform, e)
                tasks.append(asyncio.sleep(0, result={"status": "error", "platform": platform_lower, "message": str(e)}))
                platform_map[platform_lower] = len(tasks) - 1

        # gather results (allow partial failures)
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        # normalize to dict: platform -> result
        results: Dict[str, Any] = {}
        for platform, idx in platform_map.items():
            res = results_list[idx]
            # if exception, convert to dict
            if isinstance(res, Exception):
                logger.exception("Export task for %s raised: %s", platform, res)
                results[platform] = {"status": "error", "platform": platform, "message": str(res)}
            else:
                results[platform] = res

        return results
