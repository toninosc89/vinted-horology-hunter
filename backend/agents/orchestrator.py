from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from backend.agents.llm_router import USD_TO_EUR_RATE, MultiProviderLLMRouter
from backend.agents.tier0_guardrail import Tier0Guardrail
from backend.agents.tier1_screener import Tier1BatchScreener
from backend.agents.tier2_appraiser import Tier2MultimodalAppraiser
from backend.agents.tier3_arbitrator import Tier3SeniorArbitrator
from backend.database import (
    apply_canonical_valuation,
    get_cached_appraisal,
    get_cached_description,
    load_router_settings,
    reconcile_all_cached_appraisals,
    save_cached_appraisal,
)
from backend.schemas import (
    CatalogItem,
    LLMRouterSettings,
    PipelineTelemetry,
    SearchRequest,
    SearchResponse,
    WatchAppraisal,
)
from backend.vinted_client import VintedClient


class HorologyMASOrchestrator:
    """
    4-Tier Cost-Optimized Multi-Agent Orchestrator for Vinted Horology Hunter.
    Coordinates:
      - Stage 1 Catalog Search
      - Tier 0 Deterministic Regex Blacklist, Condition Filter & SQLite Cache
      - Tier 1 Batch Triage Screener (up to 20 items in 1 prompt)
      - Stage 2 Deep Item Fetch + Image Download
      - Tier 2 Multimodal Horologist & Market Appraiser
      - Tier 3 Automatic & Manual Senior Horology Arbitrator Escalation
    """

    def __init__(
        self,
        settings: Optional[LLMRouterSettings] = None,
        vinted_client: Optional[VintedClient] = None,
        db_path: Optional[Path] = None,
        enforce_stage2_jitter: bool = False,
    ) -> None:
        self.db_path = db_path
        self.settings = settings or load_router_settings(db_path=db_path)
        self.router = MultiProviderLLMRouter(self.settings)
        self.vinted_client = vinted_client or VintedClient()
        self.enforce_stage2_jitter = enforce_stage2_jitter

        self.tier1 = Tier1BatchScreener(self.router)
        self.tier2 = Tier2MultimodalAppraiser(self.router)
        self.tier3 = Tier3SeniorArbitrator(self.router)

    async def execute_search_pipeline(
        self, request: SearchRequest
    ) -> SearchResponse:
        start_ts = time.perf_counter()
        telemetry = PipelineTelemetry(query=request.query)

        # Stage 1: Fetch pool of catalog items from Vinted so Tier 0 rejections don't eat into max_items
        fetch_pool_size = min(max(request.max_items * 2, 24), 60)
        catalog_items = await self.vinted_client.search_catalog(
            search_text=request.query,
            price_to=request.max_price,
            per_page=fetch_pool_size,
            sort_order=request.sort_order,
        )
        telemetry.source_mode = self.vinted_client.last_source_mode

        # Tier 0: Deterministic Guardrail & Cache Check (until we fill request.max_items valid candidates)
        import re

        surviving_tier0: list[CatalogItem] = []
        final_appraisals: list[WatchAppraisal] = []
        seen_uncached_signatures: set[str] = set()
        inspected_count = 0

        for item in catalog_items:
            if len(surviving_tier0) + len(final_appraisals) >= request.max_items:
                break
            inspected_count += 1

            ok_regex, reason_regex = Tier0Guardrail.check_text_blacklist(
                item.title, item.status, item.description_snippet
            )
            if not ok_regex:
                telemetry.discarded_tier0_regex += 1
                telemetry.estimated_tokens_saved += 1450
                telemetry.tier0_rejection_reasons.append(
                    {"id": str(item.id), "title": item.title, "reason": reason_regex or "Regex"}
                )
                continue

            ok_cond, reason_cond = Tier0Guardrail.check_condition_status(
                item.status, item.title, item.description_snippet
            )
            if not ok_cond:
                telemetry.discarded_tier0_condition += 1
                telemetry.estimated_tokens_saved += 1450
                telemetry.tier0_rejection_reasons.append(
                    {"id": str(item.id), "title": item.title, "reason": reason_cond or "Condition"}
                )
                continue

            if not request.bypass_cache:
                cached = get_cached_appraisal(item.id, item.price, db_path=self.db_path)
                if cached is not None:
                    telemetry.cache_hits_tier0 += 1
                    telemetry.estimated_tokens_saved += 1450
                    cached_hit = cached.model_copy(
                        update={
                            "tier_reached": (
                                cached.tier_reached
                                if "Cache" in cached.tier_reached
                                else f"{cached.tier_reached} • Cache Tier 0"
                            ),
                            "tokens_used": 0,
                            "cost_usd": 0.0,
                        }
                    )
                    final_appraisals.append(cached_hit)
                    continue

            # FinOps Deduplication: Prevent identical seller reposts (same normalized title + price)
            # from triggering duplicate Stage 2 / Tier 2 Vision LLM calls in the same scan
            norm_sig = f"{re.sub(r'\\W+', '', item.title.lower())}:{int(round(item.price))}"
            if norm_sig in seen_uncached_signatures:
                telemetry.discarded_tier0_regex += 1
                telemetry.estimated_tokens_saved += 1450
                telemetry.tier0_rejection_reasons.append(
                    {
                        "id": str(item.id),
                        "title": item.title,
                        "reason": "Tier 0 FinOps Dedup: Annuncio duplicato (stesso titolo e prezzo)",
                    }
                )
                continue
            seen_uncached_signatures.add(norm_sig)

            surviving_tier0.append(item)

        telemetry.items_extracted = inspected_count

        # Tier 1: Batch Triage Screener (up to 20 surviving items, promotes top 8 max)
        approved_items: list[CatalogItem] = []
        tier1_tokens_per_item = 0
        tier1_cost_per_item = 0.0

        if surviving_tier0:
            batch_candidates = surviving_tier0[:20]
            telemetry.evaluated_tier1 = len(batch_candidates)
            triage_out, tier1_call = await self.tier1.screen_batch(batch_candidates)

            telemetry.total_tokens_used += tier1_call.total_tokens
            telemetry.total_cost_usd = round(
                telemetry.total_cost_usd + tier1_call.cost_usd, 6
            )

            approved_set = set(triage_out.approved_item_ids)
            for cand in batch_candidates:
                if cand.id in approved_set:
                    approved_items.append(cand)
                else:
                    telemetry.estimated_tokens_saved += 1200

            telemetry.promoted_tier1 = len(approved_items)
            if approved_items:
                tier1_tokens_per_item = max(1, tier1_call.total_tokens // len(approved_items))
                tier1_cost_per_item = round(tier1_call.cost_usd / len(approved_items), 6)

        # Stage 2 Deep Fetch + Tier 2 Multimodal Appraiser (Concurrent)
        import asyncio

        sem = asyncio.Semaphore(4)

        async def _process_candidate(cat_item: CatalogItem) -> Optional[WatchAppraisal]:
            async with sem:
                deep_item = await self.vinted_client.fetch_deep_item(
                    item_id=cat_item.id,
                    stage1_fallback=cat_item,
                    enforce_jitter=self.enforce_stage2_jitter,
                )

                # Re-verify full Stage 2 description against Tier 0 Blacklist before calling Vision LLM
                ok_deep_regex, reason_deep = Tier0Guardrail.check_text_blacklist(
                    deep_item.title, deep_item.status, deep_item.description
                )
                if not ok_deep_regex:
                    telemetry.discarded_tier0_regex += 1
                    telemetry.estimated_tokens_saved += 1100
                    telemetry.tier0_rejection_reasons.append(
                        {
                            "id": str(deep_item.id),
                            "title": deep_item.title,
                            "reason": f"{reason_deep} (rilevato in descrizione Stage 2)",
                        }
                    )
                    return None

                # FinOps Optimization: Download 2 photos (front dial + caseback) during bulk scans
                images_b64 = await self.vinted_client.download_images_as_base64(
                    deep_item.photo_urls, max_images=2
                )

                appraisal = await self.tier2.appraise_item(
                    deep_item=deep_item,
                    images_b64=images_b64,
                    prior_tokens=tier1_tokens_per_item,
                    prior_cost_usd=tier1_cost_per_item,
                )
                telemetry.appraised_tier2 += 1

                # Subtract shared tier1 portion when adding to global telemetry so we don't double count
                tier2_delta_tokens = max(0, appraisal.tokens_used - tier1_tokens_per_item)
                tier2_delta_cost = max(0.0, appraisal.cost_usd - tier1_cost_per_item)
                telemetry.total_tokens_used += tier2_delta_tokens
                telemetry.total_cost_usd = round(
                    telemetry.total_cost_usd + tier2_delta_cost, 6
                )

                # Automatic Tier 3 Escalation Check (disabled by default for FinOps efficiency)
                if self.tier3.should_auto_escalate(appraisal):
                    pre_t3_tokens = appraisal.tokens_used
                    pre_t3_cost = appraisal.cost_usd
                    appraisal = await self.tier3.arbitrate(
                        appraisal=appraisal,
                        description=deep_item.description,
                        images_b64=images_b64[:1],
                        trigger_mode="Auto-Escalation",
                    )
                    telemetry.escalated_tier3 += 1
                    telemetry.total_tokens_used += max(0, appraisal.tokens_used - pre_t3_tokens)
                    telemetry.total_cost_usd = round(
                        telemetry.total_cost_usd + max(0.0, appraisal.cost_usd - pre_t3_cost),
                        6,
                    )

                appraisal = save_cached_appraisal(
                    appraisal,
                    description_text=deep_item.description,
                    db_path=self.db_path,
                )
                return appraisal

        if approved_items:
            batch_results = await asyncio.gather(
                *[_process_candidate(cat_item) for cat_item in approved_items]
            )
            for res_item in batch_results:
                if res_item is not None:
                    final_appraisals.append(res_item)

        # Reconcile canonical reference valuations across all items so identical references/duplicates
        # (even when appraised concurrently in the same batch) have 100% identical market values
        reconcile_all_cached_appraisals(db_path=self.db_path)
        final_appraisals = [
            get_cached_appraisal(
                a.vinted_id, a.price_listed_eur, db_path=self.db_path
            )
            or a
            for a in final_appraisals
        ]

        # Optional UI filter: Mostra solo Marcianti Verificati (Score >= 6)
        if request.only_verified_working:
            final_appraisals = [
                a
                for a in final_appraisals
                if a.is_working_verified and a.deal_score >= 6
            ]

        # Sort cards by deal_score descending, then net_margin_potential_eur descending
        final_appraisals.sort(
            key=lambda a: (a.deal_score, a.net_margin_potential_eur),
            reverse=True,
        )

        telemetry.total_cost_eur = round(
            telemetry.total_cost_usd * USD_TO_EUR_RATE, 6
        )
        telemetry.duration_seconds = round(time.perf_counter() - start_ts, 2)

        return SearchResponse(items=final_appraisals, telemetry=telemetry)

    async def escalate_single_item_tier3(
        self,
        vinted_id: int,
        appraisal_override: Optional[WatchAppraisal] = None,
        description_override: Optional[str] = None,
    ) -> WatchAppraisal:
        """Executes on-demand Tier 3 forensic escalation when user clicks 'Esegui Perizia Forense Tier 3'."""
        base_appraisal = appraisal_override or get_cached_appraisal(
            vinted_id, db_path=self.db_path
        )
        if base_appraisal is None:
            raise ValueError(f"Nessuna perizia trovata per vinted_id={vinted_id}")

        desc = description_override or get_cached_description(
            vinted_id, db_path=self.db_path
        )
        images_b64 = await self.vinted_client.download_images_as_base64(
            base_appraisal.photo_urls, max_images=1
        )
        upgraded = await self.tier3.arbitrate(
            appraisal=base_appraisal,
            description=desc,
            images_b64=images_b64,
            trigger_mode="Manuale On-Demand",
        )
        upgraded = save_cached_appraisal(
            upgraded, description_text=desc, db_path=self.db_path
        )
        reconcile_all_cached_appraisals(db_path=self.db_path)
        return (
            get_cached_appraisal(
                upgraded.vinted_id, upgraded.price_listed_eur, db_path=self.db_path
            )
            or upgraded
        )

    async def analyze_single_url(
        self,
        raw_url: str,
        run_tier3: bool = False,
        bypass_cache: bool = True,
    ) -> WatchAppraisal:
        """
        Dedicated Direct Link Analyzer: scrapes a single Vinted item URL (or numeric ID),
        downloads high-res photos, runs Tier 2 Vision Appraisal, and optionally escalates
        immediately to Tier 3 Senior Arbitrator.
        """
        import re

        cleaned = raw_url.strip()
        id_match = re.search(r"vinted\.[a-z]+/items/(\d+)", cleaned, re.IGNORECASE)
        if id_match:
            item_id = int(id_match.group(1))
            page_url = cleaned.split("?")[0]
        elif cleaned.isdigit():
            item_id = int(cleaned)
            page_url = f"https://www.vinted.it/items/{item_id}"
        else:
            raise ValueError(
                "Inserisci un link Vinted valido (es. https://www.vinted.it/items/10298557299-...) oppure l'ID numerico dell'annuncio."
            )

        if not bypass_cache and not run_tier3:
            cached = get_cached_appraisal(item_id, db_path=self.db_path)
            if cached is not None:
                return cached

        stub = CatalogItem(
            id=item_id,
            title=f"Orologio Vinted #{item_id}",
            price=0.0,
            brand_title="",
            status="Ottimo",
            url=page_url,
        )
        deep_item = await self.vinted_client.fetch_deep_item(
            item_id=item_id,
            stage1_fallback=stub,
            enforce_jitter=False,
        )

        images_b64 = await self.vinted_client.download_images_as_base64(
            deep_item.photo_urls, max_images=3
        )

        appraisal = await self.tier2.appraise_item(
            deep_item=deep_item,
            images_b64=images_b64,
        )

        if run_tier3 or self.tier3.should_auto_escalate(appraisal):
            appraisal = await self.tier3.arbitrate(
                appraisal=appraisal,
                description=deep_item.description,
                images_b64=images_b64,
                trigger_mode="Analisi Link Diretto",
            )
        else:
            appraisal = appraisal.model_copy(
                update={"tier_reached": f"{appraisal.tier_reached} • Link Diretto"}
            )

        appraisal = save_cached_appraisal(
            appraisal,
            description_text=deep_item.description,
            db_path=self.db_path,
        )
        reconcile_all_cached_appraisals(db_path=self.db_path)
        return (
            get_cached_appraisal(
                appraisal.vinted_id, appraisal.price_listed_eur, db_path=self.db_path
            )
            or appraisal
        )

