from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.agents.llm_router import MultiProviderLLMRouter
from backend.agents.orchestrator import HorologyMASOrchestrator
from backend.database import (
    clear_appraisal_cache,
    init_db,
    load_router_settings,
    save_router_settings,
)
from backend.schemas import (
    LLMRouterSettings,
    SearchRequest,
    SearchResponse,
    Tier3EscalationRequest,
    WatchAppraisal,
)
from backend.vinted_client import VintedClient

shared_vinted_client = VintedClient()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
    await shared_vinted_client.close()


app = FastAPI(
    title="Vinted Horology Hunter API",
    description=(
        "Sistema Multi-Agente (MAS) a 4 livelli con LLM Router Multi-Provider "
        "per lo scouting e la perizia orologiera su Vinted.it"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    settings = load_router_settings()
    return {
        "status": "ok",
        "service": "Vinted Horology Hunter",
        "tier1_model": f"{settings.tier1_provider}/{settings.tier1_model}",
        "tier2_model": f"{settings.tier2_provider}/{settings.tier2_model}",
        "tier3_model": f"{settings.tier3_provider}/{settings.tier3_model}",
    }


@app.post("/api/search", response_model=SearchResponse)
async def run_watch_search(request: SearchRequest) -> SearchResponse:
    settings = load_router_settings()
    orchestrator = HorologyMASOrchestrator(
        settings=settings,
        vinted_client=shared_vinted_client,
        enforce_stage2_jitter=False,
    )
    return await orchestrator.execute_search_pipeline(request)


@app.post("/api/tier3/{vinted_id}", response_model=WatchAppraisal)
async def run_tier3_escalation(
    vinted_id: int, payload: Tier3EscalationRequest
) -> WatchAppraisal:
    settings = load_router_settings()
    orchestrator = HorologyMASOrchestrator(
        settings=settings,
        vinted_client=shared_vinted_client,
    )
    try:
        return await orchestrator.escalate_single_item_tier3(
            vinted_id=vinted_id,
            appraisal_override=payload.appraisal,
            description_override=payload.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/settings", response_model=LLMRouterSettings)
async def get_settings() -> LLMRouterSettings:
    return load_router_settings()


@app.post("/api/settings", response_model=LLMRouterSettings)
async def update_settings(settings: LLMRouterSettings) -> LLMRouterSettings:
    return save_router_settings(settings)


@app.post("/api/settings/auto-optimize", response_model=LLMRouterSettings)
async def auto_optimize_router(settings: LLMRouterSettings) -> LLMRouterSettings:
    router = MultiProviderLLMRouter(settings)
    optimized = router.auto_optimize_settings()
    return save_router_settings(optimized)


@app.delete("/api/cache")
async def flush_cache() -> dict[str, Any]:
    deleted = clear_appraisal_cache()
    return {"status": "cleared", "deleted_entries": deleted}
