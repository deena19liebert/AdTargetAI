import json
import logging
from datetime import datetime
from typing import Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)

class CampaignExporter:
    """
    Advanced campaign exporter that generates production-ready files and API responses
    """
    
    def __init__(self, output_dir: str = "exports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Export templates for different platforms
        self.export_templates = {
            "facebook": self._facebook_export_template,
            "google": self._google_export_template,
            "tiktok": self._tiktok_export_template,
            "instagram": self._instagram_export_template,
            "linkedin": self._linkedin_export_template,
            "pinterest": self._pinterest_export_template,
            "twitter": self._twitter_export_template
        }

    def export_campaign_package(self, campaign_input: Dict, audience_insights: Dict, 
                              platform_feeds: Dict[str, Any], format: str = "json") -> Dict[str, Any]:
        """Export complete campaign package with metadata"""
        
        campaign_id = self._generate_campaign_id(campaign_input['product_name'])
        timestamp = datetime.now().isoformat()
        
        package = {
            "metadata": {
                "campaign_id": campaign_id,
                "export_timestamp": timestamp,
                "version": "1.0",
                "status": "ready_for_review"
            },
            "campaign_input": campaign_input,
            "audience_insights": audience_insights,
            "platform_feeds": platform_feeds,
            "export_summary": self._generate_export_summary(platform_feeds),
            "validation_results": self._validate_exports(platform_feeds)
        }
        
        # Generate exports based on format
        if format == "json":
            return self._export_json_package(package, campaign_id)
        elif format == "files":
            return self._export_file_package(package, campaign_id)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def _export_json_package(self, package: Dict[str, Any], campaign_id: str) -> Dict[str, Any]:
        """Export as single JSON package"""
        
        # Add download URLs
        package["download_links"] = {
            "complete_package": f"/api/campaigns/{campaign_id}/download",
            "individual_feeds": {
                platform: f"/api/campaigns/{campaign_id}/feeds/{platform}" 
                for platform in package['platform_feeds'].keys()
            }
        }
        
        logger.info(f"Exported JSON package for campaign: {campaign_id}")
        return package

    def _export_file_package(self, package: Dict[str, Any], campaign_id: str) -> Dict[str, Any]:
        """Export as multiple files in a structured directory"""
        
        campaign_dir = self.output_dir / campaign_id
        campaign_dir.mkdir(exist_ok=True)
        
        # Export individual platform files
        exported_files = {}
        
        for platform, feed in package['platform_feeds'].items():
            filename = f"{platform}_ad_spec.json"
            filepath = campaign_dir / filename
            
            # Apply platform-specific template
            platform_export = self.export_templates.get(platform, lambda x: x)(feed)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(platform_export, f, indent=2, ensure_ascii=False)
            
            exported_files[platform] = str(filepath)
        
        # Export complete package
        complete_file = campaign_dir / "complete_campaign.json"
        with open(complete_file, 'w', encoding='utf-8') as f:
            json.dump(package, f, indent=2, ensure_ascii=False)
        
        # Export README with instructions
        self._export_readme(campaign_dir, package)
        
        logger.info(f"Exported file package for campaign: {campaign_id}")
        
        return {
            "campaign_id": campaign_id,
            "export_directory": str(campaign_dir),
            "exported_files": exported_files,
            "complete_package": str(complete_file),
            "download_instructions": self._generate_download_instructions(campaign_id)
        }

    def _facebook_export_template(self, feed: Dict[str, Any]) -> Dict[str, Any]:
        """Format Facebook export for Ads Manager"""
        return {
            "schema_version": "v12.0",
            "campaign": {
                "name": feed.get("campaign_structure", {}).get("campaign_name", "Facebook Campaign"),
                "objective": "OUTCOME_TRAFFIC",
                "status": "PAUSED"
            },
            "adset": {
                "name": feed.get("campaign_structure", {}).get("adset_name", "Targeting AdSet"),
                "daily_budget": feed.get("campaign_structure", {}).get("daily_budget", 50) * 100,  # Convert to cents
                "billing_event": "IMPRESSIONS",
                "optimization_goal": "LINK_CLICKS",
                "targeting": feed.get("targeting_spec", {})
            },
            "ad": {
                "name": feed.get("ad_creative", {}).get("name", "Ad Creative"),
                "creative": feed.get("ad_creative", {})
            }
        }

    def _google_export_template(self, feed: Dict[str, Any]) -> Dict[str, Any]:
        """Format Google Ads export"""
        return {
            "customer_id": "INSERT_CUSTOMER_ID",
            "campaign": feed.get("campaign", {}),
            "ad_groups": [{
                "name": "All Visitors",
                "keywords": feed.get("keywords", {}),
                "ads": [{
                    "type": "RESPONSIVE_SEARCH_AD",
                    "headlines": feed.get("assets", {}).get("headlines", []),
                    "descriptions": feed.get("assets", {}).get("descriptions", [])
                }]
            }],
            "audiences": feed.get("audience", {})
        }

    def _tiktok_export_template(self, feed: Dict[str, Any]) -> Dict[str, Any]:
        """Format TikTok Ads export"""
        return {
            "advertiser_id": "INSERT_ADVERTISER_ID",
            "campaign_name": f"TikTok - {feed.get('audience', {}).get('age_range', ['25-45'])[0]}",
            "objective": "CONVERSIONS",
            "budget": 5000,  # In cents
            "audience": feed.get("audience", {}),
            "creatives": [feed.get("creative", {})]
        }

    def _instagram_export_template(self, feed: Dict[str, Any]) -> Dict[str, Any]:
        """Format Instagram export"""
        return {
            "platform": "instagram",
            "targeting": feed.get("targeting", {}),
            "creative_spec": feed.get("creative", {}),
            "placement": feed.get("placement", {})
        }

    def _linkedin_export_template(self, feed: Dict[str, Any]) -> Dict[str, Any]:
        """Format LinkedIn export"""
        return {
            "account_id": "INSERT_ACCOUNT_ID",
            "campaign": feed.get("campaign", {}),
            "targeting": feed.get("targeting", {}),
            "creative": feed.get("creative", {})
        }

    def _pinterest_export_template(self, feed: Dict[str, Any]) -> Dict[str, Any]:
        """Format Pinterest export"""
        return {
            "ad_account_id": "INSERT_AD_ACCOUNT_ID",
            "campaign": {
                "name": "Pinterest Awareness Campaign",
                "status": "ACTIVE"
            },
            "targeting": feed.get("targeting", {}),
            "creative": feed.get("creative", {})
        }

    def _twitter_export_template(self, feed: Dict[str, Any]) -> Dict[str, Any]:
        """Format Twitter export"""
        return {
            "account_id": "INSERT_ACCOUNT_ID",
            "campaign": feed.get("campaign", {}),
            "targeting": feed.get("targeting", {}),
            "creative": feed.get("creative", {})
        }

    def _generate_campaign_id(self, product_name: str) -> str:
        """Generate unique campaign ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_name = "".join(c for c in product_name.lower() if c.isalnum())[:20]
        return f"campaign_{clean_name}_{timestamp}"

    def _generate_export_summary(self, platform_feeds: Dict[str, Any]) -> Dict[str, Any]:
        """Generate export summary"""
        platforms = list(platform_feeds.keys())
        total_platforms = len(platforms)
        
        return {
            "total_platforms": total_platforms,
            "platforms_exported": platforms,
            "estimated_reach": "100K-500K",  # This could be calculated based on audience size
            "recommended_budget_allocation": self._calculate_budget_allocation(platform_feeds),
            "export_status": "complete",
            "next_steps": [
                "Review generated specifications",
                "Upload to respective ad platforms",
                "Set up conversion tracking",
                "Launch and monitor performance"
            ]
        }

    def _calculate_budget_allocation(self, platform_feeds: Dict[str, Any]) -> Dict[str, float]:
        """Calculate recommended budget allocation across platforms"""
        # Simple allocation logic - can be enhanced
        total_platforms = len(platform_feeds)
        if total_platforms == 0:
            return {}
            
        base_allocation = 100 / total_platforms
        allocations = {}
        
        # Weight platforms based on typical performance
        platform_weights = {
            "facebook": 1.2,
            "instagram": 1.1,
            "google": 1.3,
            "tiktok": 1.0,
            "pinterest": 0.8,
            "linkedin": 1.5,  # Higher cost platform
            "twitter": 0.9
        }
        
        for platform in platform_feeds.keys():
            weight = platform_weights.get(platform, 1.0)
            allocations[platform] = round(base_allocation * weight, 1)
        
        # Normalize to 100%
        total = sum(allocations.values())
        return {k: round((v / total) * 100, 1) for k, v in allocations.items()}

    def _validate_exports(self, platform_feeds: Dict[str, Any]) -> Dict[str, Any]:
        """Validate all exports"""
        validation_results = {}
        
        for platform, feed in platform_feeds.items():
            validation_results[platform] = {
                "has_targeting": "targeting" in str(feed).lower() or "targeting_spec" in feed,
                "has_creative": "creative" in str(feed).lower() or "ad_creative" in feed,
                "has_budget": any(key in str(feed) for key in ["budget", "daily_budget", "billing"]),
                "feed_size": len(str(feed)),
                "status": "valid" if self._validate_feed_structure(platform, feed) else "needs_review"
            }
        
        return validation_results

    def _validate_feed_structure(self, platform: str, feed: Dict[str, Any]) -> bool:
        """Validate feed structure for specific platform"""
        required_sections = {
            "facebook": ["targeting_spec", "ad_creative"],
            "instagram": ["targeting", "creative"],
            "tiktok": ["audience", "creative"],
            "google": ["campaign", "audience"],
            "linkedin": ["targeting", "creative"],
            "pinterest": ["targeting", "creative"],
            "twitter": ["targeting", "creative"]
        }
        
        if platform not in required_sections:
            return False
            
        return any(section in feed for section in required_sections[platform])

    def _export_readme(self, campaign_dir: Path, package: Dict[str, Any]):
        """Export README with instructions"""
        readme_content = f"""
# Campaign Export Package

## Campaign ID: {package['metadata']['campaign_id']}
## Generated: {package['metadata']['export_timestamp']}

## Platform Specifications Generated:
{chr(10).join(f"- {platform.upper()}: {campaign_dir}/{platform}_ad_spec.json" for platform in package['platform_feeds'].keys())}

## Next Steps:

1. **Review Specifications**: Check each platform's JSON file for accuracy
2. **Platform Setup**: 
   - Facebook: Use Business Manager → Ad Creation → Import JSON
   - Google: Use Google Ads Editor → Import Campaign
   - TikTok: Use TikTok Ads Manager → Create Campaign → Import
3. **Budget Allocation**: {package['export_summary']['recommended_budget_allocation']}
4. **Launch Sequence**: Start with 1-2 platforms, then expand based on performance

## Validation Results:
{chr(10).join(f"- {platform}: {result['status']}" for platform, result in package['validation_results'].items())}

## Support:
For questions about these exports, contact your marketing team or refer to platform-specific documentation.
"""
        
        with open(campaign_dir / "README.md", 'w', encoding='utf-8') as f:
            f.write(readme_content)

    def _generate_download_instructions(self, campaign_id: str) -> str:
        """Generate download instructions"""
        return f"""
Your campaign exports are ready!

Access your files:
1. Local files: ./exports/{campaign_id}/
2. Individual platform specs available as separate JSON files
3. Complete package: complete_campaign.json

Upload instructions for each platform are included in the README.md file.
"""

    def get_export_formats(self) -> Dict[str, Any]:
        """Get available export formats"""
        return {
            "json": "Single JSON package with all data",
            "files": "Multiple files organized by platform",
            "platforms_supported": list(self.export_templates.keys()),
            "output_directory": str(self.output_dir)
        }