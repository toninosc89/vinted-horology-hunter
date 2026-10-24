from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.agents.llm_router import MultiProviderLLMRouter
from backend.agents.orchestrator import HorologyMASOrchestrator
from backend.database import (
    clear_appraisal_cache,
    clear_heuristic_only_cache,
    init_db,
    list_cached_appraisals,
    load_router_settings,
    reconcile_all_cached_appraisals,
    save_router_settings,
)
from backend.notifier import WatchAlertNotifier, WatchRadarScheduler
from backend.schemas import (
    AlertSchedulerConfig,
    AnalyzeUrlRequest,
    LLMRouterSettings,
    PipelineTelemetry,
    SchedulerStatusResponse,
    SearchRequest,
    SearchResponse,
    Tier3EscalationRequest,
    WatchAppraisal,
)
from backend.vinted_client import VintedClient

shared_vinted_client = VintedClient()
shared_scheduler = WatchRadarScheduler(vinted_client=shared_vinted_client)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    reconcile_all_cached_appraisals()
    shared_scheduler.start_background_loop()
    yield
    await shared_scheduler.stop_background_loop()
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


@app.get("/api/cached-items", response_model=SearchResponse)
async def get_cached_items(limit: int = 30) -> SearchResponse:
    cached_items = list_cached_appraisals(limit=limit)
    telemetry = PipelineTelemetry(
        query="Cache SQLite (0 Token)",
        source_mode="live",
        items_extracted=len(cached_items),
        cache_hits_tier0=len(cached_items),
        estimated_tokens_saved=len(cached_items) * 1450,
        total_tokens_used=0,
        total_cost_usd=0.0,
        total_cost_eur=0.0,
        duration_seconds=0.01,
    )
    return SearchResponse(items=cached_items, telemetry=telemetry)


@app.post("/api/search", response_model=SearchResponse)
async def run_watch_search(request: SearchRequest) -> SearchResponse:
    settings = load_router_settings()
    orchestrator = HorologyMASOrchestrator(
        settings=settings,
        vinted_client=shared_vinted_client,
        enforce_stage2_jitter=False,
    )
    return await orchestrator.execute_search_pipeline(request)


@app.post("/api/analyze-url", response_model=WatchAppraisal)
async def analyze_single_vinted_url(request: AnalyzeUrlRequest) -> WatchAppraisal:
    settings = load_router_settings()
    orchestrator = HorologyMASOrchestrator(
        settings=settings,
        vinted_client=shared_vinted_client,
        enforce_stage2_jitter=False,
    )
    try:
        return await orchestrator.analyze_single_url(
            raw_url=request.url,
            run_tier3=request.run_tier3,
            bypass_cache=request.bypass_cache,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@app.get("/api/scheduler/status", response_model=SchedulerStatusResponse)
async def get_scheduler_status() -> SchedulerStatusResponse:
    return shared_scheduler.get_status()


@app.post("/api/scheduler/config", response_model=SchedulerStatusResponse)
async def update_scheduler_config(
    config: AlertSchedulerConfig,
) -> SchedulerStatusResponse:
    shared_scheduler.update_config(config)
    shared_scheduler.start_background_loop()
    return shared_scheduler.get_status()


@app.post("/api/scheduler/run-now")
async def trigger_scheduler_run_now(
    config: AlertSchedulerConfig,
) -> dict[str, Any]:
    shared_scheduler.update_config(config)
    shared_scheduler.start_background_loop()
    cycle_result = await shared_scheduler.execute_radar_cycle()
    return {
        "cycle": cycle_result,
        "status": shared_scheduler.get_status().model_dump(),
    }


@app.post("/api/scheduler/test-alert")
async def send_test_alert(config: AlertSchedulerConfig) -> dict[str, Any]:
    shared_scheduler.update_config(config)
    cached = list_cached_appraisals(limit=1)
    if cached:
        sample = cached[0]
    else:
        sample = WatchAppraisal(
            vinted_id=10298557299,
            title="Orient Star Classic Automatic Power Reserve RE-AU0006S00B",
            price_listed_eur=195.0,
            total_vinted_cost_eur=209.95,
            url="https://www.vinted.it/items/10298557299-relogio-orient-star-re-au0006s00b",
            photo_urls=[],
            identified_brand_model="Orient Star Contemporary Automatic 50h",
            estimated_reference_caliber="Calibro In-House F6N43 (Ref. RE-AU0006S00B)",
            is_working_verified=True,
            working_status_notes="Test Alert: Perfettamente marciante",
            franken_fake_risk="LOW",
            authenticity_notes="Test notifica Telegram / WhatsApp attiva",
            estimated_market_value_eur_min=340.0,
            estimated_market_value_eur_max=430.0,
            net_margin_potential_eur=175.05,
            deal_score=9,
            confidence_score=0.95,
            recommended_action="COMPRA_SUBITO",
            suggested_offer_eur=175.0,
            tier_reached="Test Radar Alert",
            model_used="Radar Notifier",
            tokens_used=0,
            cost_usd=0.0,
            roi_pct=83.4,
        )

    entry = await WatchAlertNotifier.dispatch_alert(
        config=config,
        appraisal=sample,
        record_in_db=True,
    )
    return {
        "ok": True,
        "entry": entry.model_dump(),
        "status": shared_scheduler.get_status().model_dump(),
    }


@app.get("/api/settings", response_model=LLMRouterSettings)
async def get_settings() -> LLMRouterSettings:
    return load_router_settings()


@app.post("/api/settings", response_model=LLMRouterSettings)
async def update_settings(settings: LLMRouterSettings) -> LLMRouterSettings:
    clear_heuristic_only_cache()
    return save_router_settings(settings)


@app.post("/api/settings/auto-optimize", response_model=LLMRouterSettings)
async def auto_optimize_router(settings: LLMRouterSettings) -> LLMRouterSettings:
    clear_heuristic_only_cache()
    router = MultiProviderLLMRouter(settings)
    optimized = router.auto_optimize_settings()
    return save_router_settings(optimized)


@app.post("/api/settings/test")
async def test_router_connection(settings: LLMRouterSettings) -> dict[str, Any]:
    import time

    router = MultiProviderLLMRouter(settings)
    provider = settings.tier2_provider
    model = settings.tier2_model
    api_key = router.get_api_key_for_provider(provider)
    if not api_key:
        return {
            "ok": False,
            "provider": provider,
            "model": model,
            "message": f"Nessuna chiave API inserita per il provider '{provider.upper()}'.",
        }

    t0 = time.perf_counter()
    try:
        res = await router._dispatch_provider(
            provider=provider,
            model=model,
            api_key=api_key,
            system_prompt="Sei un assistente orologiero. Rispondi solo in JSON.",
            user_prompt='Restituisci {"status": "attivo", "messaggio": "Connessione LLM verificata"}',
            images=None,
        )
        latency_ms = round((time.perf_counter() - t0) * 1000)
        return {
            "ok": True,
            "provider": res.provider_used,
            "model": res.model_used,
            "latency_ms": latency_ms,
            "tokens": res.total_tokens,
            "message": f"Connessione LIVE attiva! Modello risponde in {latency_ms}ms: {res.model_used}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider,
            "model": model,
            "message": f"Errore chiamata API ({provider}/{model}): {str(exc)[:180]}",
        }


@app.delete("/api/cache")
async def flush_cache() -> dict[str, Any]:
    deleted = clear_appraisal_cache()
    return {"status": "cleared", "deleted_entries": deleted}

