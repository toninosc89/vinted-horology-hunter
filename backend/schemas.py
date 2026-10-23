from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class WatchAppraisal(BaseModel):
    vinted_id: int
    title: str
    price_listed_eur: float
    total_vinted_cost_eur: float
    url: str
    photo_urls: list[str]
    identified_brand_model: str
    estimated_reference_caliber: str
    is_working_verified: bool
    working_status_notes: str
    franken_fake_risk: Literal["LOW", "MEDIUM", "HIGH"]
    authenticity_notes: str
    estimated_market_value_eur_min: float
    estimated_market_value_eur_max: float
    net_margin_potential_eur: float
    deal_score: int = Field(ge=1, le=10)
    confidence_score: float = Field(ge=0.0, le=1.0)
    recommended_action: Literal[
        "COMPRA_SUBITO", "CHIEDI_FOTO_FONDELLO", "TRATTA_PREZZO", "SCARTA"
    ]
    suggested_offer_eur: Optional[float] = None
    suggested_message_to_seller: Optional[str] = None
    tier_reached: str
    model_used: str
    tokens_used: int
    cost_usd: float


class CatalogItem(BaseModel):
    id: int
    title: str
    price: float
    brand_title: str = ""
    status: str = ""
    url: str
    photo_url: str = ""
    extra_photo_urls: list[str] = Field(default_factory=list)
    description_snippet: str = ""


class DeepItemData(BaseModel):
    id: int
    title: str
    price: float
    brand_title: str = ""
    status: str = ""
    url: str
    description: str = ""
    photo_urls: list[str] = Field(default_factory=list)
    seller_username: str = ""
    source_stage: str = "stage2_api"


class Tier1TriageCandidate(BaseModel):
    id: int
    triage_note: str
    priority_rank: int = 1


class Tier1BatchOutput(BaseModel):
    approved_item_ids: list[int] = Field(default_factory=list)
    triage_notes: dict[str, str] = Field(default_factory=dict)


class PipelineTelemetry(BaseModel):
    query: str
    source_mode: str = "live"  # "live" or "fallback_catalog"
    items_extracted: int = 0
    discarded_tier0_regex: int = 0
    discarded_tier0_condition: int = 0
    cache_hits_tier0: int = 0
    evaluated_tier1: int = 0
    promoted_tier1: int = 0
    appraised_tier2: int = 0
    escalated_tier3: int = 0
    total_tokens_used: int = 0
    estimated_tokens_saved: int = 0
    total_cost_usd: float = 0.0
    total_cost_eur: float = 0.0
    duration_seconds: float = 0.0
    tier0_rejection_reasons: list[dict[str, str]] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str = Field(default="seiko vintage", min_length=1)
    max_price: Optional[float] = Field(default=250.0, gt=0)
    max_items: int = Field(default=16, ge=1, le=50)
    only_verified_working: bool = Field(default=False)
    bypass_cache: bool = Field(default=False)


class SearchResponse(BaseModel):
    items: list[WatchAppraisal]
    telemetry: PipelineTelemetry


class LLMRouterSettings(BaseModel):
    gemini_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    groq_api_key: str = ""
    deepseek_api_key: str = ""
    openrouter_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    tier1_provider: str = "gemini"
    tier1_model: str = "gemini-2.5-flash-lite"
    tier2_provider: str = "gemini"
    tier2_model: str = "gemini-2.5-flash"
    tier3_provider: str = "gemini"
    tier3_model: str = "gemini-4-argon"
    auto_optimize_enabled: bool = True


class Tier3EscalationRequest(BaseModel):
    appraisal: Optional[WatchAppraisal] = None
    description: Optional[str] = None
