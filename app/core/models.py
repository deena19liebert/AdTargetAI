from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, validator

class Platform(str, Enum):
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram" 
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    LINKEDIN = "linkedin"
    X = "x"
    SNAPCHAT = "snapchat"
    GOOGLE = "google"
    PINTEREST = "pinterest"

class CampaignInput(BaseModel):
    product_name: str = Field(..., min_length=1, max_length=100)
    product_description: str = Field(..., min_length=10, max_length=500)
    category: str = Field(..., min_length=2, max_length=50)
    price_range: str = Field(..., description="e.g., budget, mid-range, premium, luxury")
    platforms: List[Platform]
    target_location: List[str] = Field(default_factory=lambda: ["US"])
    daily_budget: float = Field(..., gt=0)
    campaign_days: int = Field(..., gt=0, le=365)
    call_to_action: str = Field(..., min_length=2, max_length=50)
    reference_description: Optional[str] = Field(None, max_length=300)
    image_url: Optional[str] = None
    image_hash: Optional[str] = None

    
    @property
    def total_budget(self) -> float:
        return self.daily_budget * self.campaign_days

class AudienceInsights(BaseModel):
    age_min: int = Field(..., ge=13, le=80)
    age_max: int = Field(..., ge=13, le=80)
    genders: List[str]
    interests: List[str]
    behaviors: List[str]
    locations: List[str]
    languages: List[str]
    suggested_ctas: List[str]
    campaign_objectives: List[str]
    platform_recommendations: Dict[str, str]
    ideal_posting_times: Dict[str, List[str]]
    
    @validator('age_max')
    def validate_age_range(cls, v, values):
        if 'age_min' in values and v <= values['age_min']:
            raise ValueError('age_max must be greater than age_min')
        return v