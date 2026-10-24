from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from backend.agents.llm_router import MultiProviderLLMRouter
from backend.agents.orchestrator import HorologyMASOrchestrator
from backend.agents.tier0_guardrail import Tier0Guardrail
from backend.schemas import (
    CatalogItem,
    LLMRouterSettings,
    SearchRequest,
    WatchAppraisal,
)
from backend.vinted_client import VintedClient


def test_tier0_regex_10_tricky_italian_watch_titles() -> None:
    """
    Tests Tier 0 Regex filtering against 10 tricky Italian broken/battery-dead watch titles
    (ensuring all 10 broken/battery-dead watches are caught) AND verifies working watches pass.
    """
    tricky_broken_titles = [
        "1. Seiko 5 Automatico vintage anni 70 - NON FUNZIONANTE",
        "2. Orologio Citizen Promaster subacqueo da revisionare",
        "3. Cronografo meccanico svizzero Landeron per ricambi",
        "4. Orient automatico vintage fermo in cassetto da anni",
        "5. Seiko Quartz vintage con batteria da cambiare",
        "6. Bellissimo Tissot PR50 ma con pila scarica",
        "7. Orologio vintage Seiko 6139 rotto / difettoso",
        "8. Citizen Eco-Drive non marciante senza batteria",
        "9. Solo cassa e solo quadrante Seiko 7009 per progetto",
        "10. Lotto / blocco 5 orologi vintage spares or repair not working",
    ]

    for title in tricky_broken_titles:
        is_valid, reason = Tier0Guardrail.check_text_blacklist(title=title, status="Buono")
        assert not is_valid, f"Expected broken watch title to be rejected by Tier 0: {title}"
        assert reason is not None and "Tier 0 Regex Blacklist" in reason

    working_titles = [
        "Seiko 5 Sports Speed-Timer 6139-6002 Cronografo Automatico Marciante",
        "Orient Star Classic Automatic Power Reserve SAF02004W0 Perfetto",
        "Citizen Promaster Diver Automatico NY0040-09E Revisionato",
        "Seiko King Quartz 4823-8000 Vintage 1977 Batteria Nuova",
    ]

    for title in working_titles:
        is_valid, reason = Tier0Guardrail.check_text_blacklist(title=title, status="Ottimo")
        assert is_valid, f"Expected working watch title to pass Tier 0: {title} (reason={reason})"


def test_tier0_condition_filter() -> None:
    """Verifies Tier 0 condition filter rejects 'Scarso' and 'Satisfactory' with defects."""
    ok_scarso, reason_scarso = Tier0Guardrail.check_condition_status("Scarso", "Seiko 5")
    assert not ok_scarso
    assert reason_scarso is not None

    ok_sat, reason_sat = Tier0Guardrail.check_condition_status(
        "Satisfactory", "Seiko Automatico", "Presenta ruggine e ritarda molto"
    )
    assert not ok_sat
    assert reason_sat is not None

    ok_good, _ = Tier0Guardrail.check_condition_status("Ottimo", "Orient Star Automatico")
    assert ok_good


@pytest.mark.asyncio
async def test_vinted_client_handshake_and_stage1_parsing() -> None:
    """
    Tests VintedClient session handshake, price/field normalization, and Stage 1 search parsing
    (with clean mock fallback if sandbox network blocks Vinted).
    """
    raw_nested = {
        "id": 998877,
        "title": "Seiko 6139 Pogue Vintage",
        "price": {"amount": "175,50", "currency_code": "EUR"},
        "brand_title": "Seiko",
        "status": "Ottimo",
        "url": "/items/998877-seiko-6139",
        "photo": {"url": "https://images1.vinted.net/t/sample.jpg"},
    }
    normalized = VintedClient.normalize_catalog_item(raw_nested)
    assert normalized.id == 998877
    assert normalized.price == 175.50
    assert normalized.brand_title == "Seiko"
    assert normalized.url.startswith("https://www.vinted.it/items/998877")

    client = VintedClient(stage2_delay_range=(0.01, 0.02), allow_fallback_on_block=True)
    try:
        items = await client.search_catalog("seiko vintage", price_to=250.0, per_page=10)
        assert len(items) > 0
        for item in items:
            assert isinstance(item, CatalogItem)
            assert item.price <= 250.0
            assert item.title != ""
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_llm_router_fallback_and_full_orchestrator_schema() -> None:
    """
    Tests Multi-Provider LLM Router fallback logic, Auto-Optimize preset, SQLite cache hit,
    and strict WatchAppraisal Pydantic schema validation across all 4 tiers.
    """
    settings = LLMRouterSettings(
        gemini_api_key="",
        groq_api_key="gsk_test_dummy_key_for_preset_check",
    )
    router = MultiProviderLLMRouter(settings)
    optimized = router.auto_optimize_settings()
    assert optimized.tier1_provider == "groq"
    assert optimized.tier1_model == "llama-3.3-70b-versatile"

    # Now test full 4-tier orchestrator with clean temporary SQLite DB and fallback LLM routing
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db = Path(tmpdir) / "test_horology.db"
        clean_settings = LLMRouterSettings()  # triggers clean fallback chain
        client = VintedClient(stage2_delay_range=(0.01, 0.02), allow_fallback_on_block=True)
        try:
            # Force fallback catalog to deterministically verify all 4 tiers
            items = client._generate_fallback_catalog("seiko vintage", 250.0, 12)
            assert len(items) >= 8

            async def _deterministic_catalog(search_text: str, price_to=250.0, per_page=12, page=1, sort_order="smart_relevance"):
                client.last_source_mode = "fallback_catalog"
                return client._generate_fallback_catalog(search_text, price_to, per_page)

            client.search_catalog = _deterministic_catalog  # type: ignore

            orchestrator = HorologyMASOrchestrator(
                settings=clean_settings,
                vinted_client=client,
                db_path=tmp_db,
                enforce_stage2_jitter=False,
            )

            req = SearchRequest(
                query="seiko vintage",
                max_price=250.0,
                max_items=12,
                only_verified_working=False,
            )
            response = await orchestrator.execute_search_pipeline(req)
            assert response.telemetry.items_extracted > 0
            assert (
                response.telemetry.discarded_tier0_regex
                + response.telemetry.discarded_tier0_condition
                > 0
            ), "Expected Tier 0 to discard broken/lotto items in catalog"
            assert len(response.items) > 0

            # Validate every item against WatchAppraisal schema rules and descending deal_score sort
            scores = [it.deal_score for it in response.items]
            assert scores == sorted(scores, reverse=True)

            for appraisal in response.items:
                validated = WatchAppraisal.model_validate(appraisal.model_dump())
                assert 1 <= validated.deal_score <= 10
                assert 0.0 <= validated.confidence_score <= 1.0
                assert validated.franken_fake_risk in ("LOW", "MEDIUM", "HIGH")
                assert validated.recommended_action in (
                    "COMPRA_SUBITO",
                    "CHIEDI_FOTO_FONDELLO",
                    "TRATTA_PREZZO",
                    "SCARTA",
                )

            # Test Manual Tier 3 Escalation on top watch card
            top_watch = response.items[0]
            escalated = await orchestrator.escalate_single_item_tier3(
                vinted_id=top_watch.vinted_id,
                appraisal_override=top_watch,
            )
            assert "Tier 3" in escalated.tier_reached
            assert escalated.confidence_score >= top_watch.confidence_score

            # Second run should hit SQLite Tier 0 Cache with 0 new tokens for cached items
            second_response = await orchestrator.execute_search_pipeline(req)
            assert second_response.telemetry.cache_hits_tier0 > 0
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_fastapi_endpoints_e2e() -> None:
    """Tests FastAPI endpoints (/api/health, /api/cached-items, /api/settings, /api/settings/auto-optimize, /api/search, /api/tier3)."""
    import httpx
    from backend.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r_health = await client.get("/api/health")
        assert r_health.status_code == 200
        assert r_health.json()["status"] == "ok"

        r_cached = await client.get("/api/cached-items?limit=10")
        assert r_cached.status_code == 200
        assert r_cached.json()["telemetry"]["total_cost_usd"] == 0.0

        r_settings = await client.get("/api/settings")
        assert r_settings.status_code == 200
        settings_data = r_settings.json()

        r_opt = await client.post("/api/settings/auto-optimize", json=settings_data)
        assert r_opt.status_code == 200
        assert r_opt.json()["auto_optimize_enabled"] is True
        assert r_opt.json()["tier2_model"] == "gemini-3.1-flash-lite-preview"

        r_search = await client.post(
            "/api/search",
            json={
                "query": "orient star",
                "max_price": 250.0,
                "max_items": 10,
                "only_verified_working": True,
                "bypass_cache": False,
            },
        )
        assert r_search.status_code == 200
        payload = r_search.json()
        assert "items" in payload and "telemetry" in payload
        assert len(payload["items"]) > 0
        for item in payload["items"]:
            assert item["is_working_verified"] is True
            assert item["deal_score"] >= 6

        first_item = payload["items"][0]
        r_t3 = await client.post(
            f"/api/tier3/{first_item['vinted_id']}",
            json={"appraisal": first_item},
        )
        assert r_t3.status_code == 200
        assert "Tier 3" in r_t3.json()["tier_reached"]

        # Test Radar Scheduler & Telegram/WhatsApp Notification Engine
        r_sched_status = await client.get("/api/scheduler/status")
        assert r_sched_status.status_code == 200
        sched_cfg = r_sched_status.json()["config"]
        sched_cfg["interval_minutes"] = 10
        sched_cfg["query"] = "Orient Star"

        r_sched_save = await client.post("/api/scheduler/config", json=sched_cfg)
        assert r_sched_save.status_code == 200
        assert r_sched_save.json()["config"]["interval_minutes"] == 10

        r_test_alert = await client.post("/api/scheduler/test-alert", json=sched_cfg)
        assert r_test_alert.status_code == 200
        alert_data = r_test_alert.json()
        assert alert_data["ok"] is True
        assert "https://wa.me/" in alert_data["entry"]["whatsapp_quick_link"]
        assert "vinted.it/items/" in alert_data["entry"]["url"]



if __name__ == "__main__":
    print("Running Vinted Horology Hunter Pre-Flight & Pipeline Verification...")
    test_tier0_regex_10_tricky_italian_watch_titles()
    print("[PASS] Tier 0 Regex Blacklist (10 tricky Italian broken watch titles + working titles)")
    test_tier0_condition_filter()
    print("[PASS] Tier 0 Condition Filter")
    asyncio.run(test_vinted_client_handshake_and_stage1_parsing())
    print("[PASS] VintedClient Handshake & Stage 1 Catalog Normalization")
    asyncio.run(test_llm_router_fallback_and_full_orchestrator_schema())
    print("[PASS] MultiProviderLLMRouter, 4-Tier MAS Orchestrator, Tier 3 Escalation & SQLite Cache")
    asyncio.run(test_fastapi_endpoints_e2e())
    print("[PASS] FastAPI REST Endpoints E2E (/api/health, /api/settings, /api/search, /api/tier3)")
    print("ALL VERIFICATION CHECKS PASSED SUCCESSFULLY!")
