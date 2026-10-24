from __future__ import annotations

import json
import re
from typing import Any

from backend.agents.llm_router import LLMCallResult, MultiProviderLLMRouter
from backend.schemas import CatalogItem, Tier1BatchOutput

FASHION_JUNK_BRANDS = re.compile(
    r"\b(daniel\s*wellington|dw|mvmt|michael\s*kors|armani\s*exchange|emporio\s*armani|"
    r"calvin\s*klein|diesel|guess|fossil\s*fashion|tommy\s*hilfiger|hugo\s*boss|ops|"
    r"hip\s*hop|cluse|rosefield|vincero|curren|poedagar|lige|naviforce|benyar|winner)\b",
    re.IGNORECASE,
)

TIER1_SYSTEM_PROMPT = """Sei l'Agente Tier 1 (Batch Triage Screener) di Vinted Horology Hunter.
Ricevi una lista JSON compatta (fino a 20 annunci) di orologi sopravvissuti al filtro deterministico Tier 0.
Il tuo compito (Ottimizzazione FinOps):
1. SCARTARE IMMEDIATAMENTE qualsiasi oggetto che NON sia un vero orologio da polso completo (es. cinturini, scatole vuote, maglie di ricambio, bracciali, abbigliamento, sveglie, occhiali).
2. Scartare orologi fashion/moda privi di valore collezionistico (es. Daniel Wellington, MVMT, Michael Kors, hommage cinesi ultra-economici), quarzi banali prezzati come meccanici, o annunci troppo vaghi/sospetti ("non testato", "non so se funziona").
3. Selezionare e promuovere al Tier 2 AL MASSIMO I MIGLIORI 8 CANDIDATI (Top 8) con il più alto potenziale di margine/collezionismo (es. Seiko vintage 6139/5606/6106/7009/7S26/Kinetic/King Quartz, Orient Star, Orient 3 Star, Citizen Promaster/Aqualand/Eco-Drive, cronografi meccanici svizzeri, Tissot, Hamilton, ecc.).
4. Rispondi ESCLUSIVAMENTE con un oggetto JSON valido con questa struttura:
{
  "approved_item_ids": [123, 456],
  "triage_notes": {
    "123": "Nota sintetica in italiano sul motivo della promozione",
    "789": "Scartato: cinturino/accessorio o orologio fashion privo di interesse"
  }
}"""

MAX_TIER1_PROMOTIONS = 8


class Tier1BatchScreener:
    """
    TIER 1: Batch Triage Screener Agent (Ultra-Low-Cost Text Model).
    Processes up to 20 Stage 1 items in a single batch prompt and promotes at most the top 8 candidates.
    """

    def __init__(self, router: MultiProviderLLMRouter) -> None:
        self.router = router

    async def screen_batch(
        self, items: list[CatalogItem], max_promotions: int = MAX_TIER1_PROMOTIONS
    ) -> tuple[Tier1BatchOutput, LLMCallResult]:
        batch = items[:20]
        compact_payload = [
            {
                "id": item.id,
                "title": item.title,
                "brand": item.brand_title,
                "price": item.price,
                "status": item.status,
            }
            for item in batch
        ]
        user_prompt = (
            f"Valuta questo batch di annunci Vinted ({len(batch)} elementi) e seleziona AL MASSIMO {max_promotions} ID "
            "con il miglior rapporto qualità/prezzo da promuovere all'analisi multimodale Tier 2:\n"
            + json.dumps(compact_payload, ensure_ascii=False)
        )

        def heuristic_fallback() -> dict[str, Any]:
            approved_ids: list[int] = []
            notes: dict[str, str] = {}
            for it in batch:
                blob = f"{it.title} {it.brand_title}".lower()
                if FASHION_JUNK_BRANDS.search(blob):
                    notes[str(it.id)] = (
                        "Scartato Tier 1: marchio fashion/quarzo commerciale senza interesse orologiero."
                    )
                    continue
                if "moda" in blob and "quarzo" in blob and it.price > 25:
                    notes[str(it.id)] = (
                        "Scartato Tier 1: orologio moda al quarzo sovrapprezzato."
                    )
                    continue
                if len(approved_ids) < max_promotions:
                    approved_ids.append(it.id)
                    notes[str(it.id)] = (
                        "Promosso Tier 1: referenza di interesse orologiero meritevole di perizia visiva Stage 2."
                    )
                else:
                    notes[str(it.id)] = (
                        "Scartato Tier 1 (Cap FinOps): priorità inferiore rispetto ai Top candidati del batch."
                    )
            return {
                "approved_item_ids": approved_ids,
                "triage_notes": notes,
            }

        call_result = await self.router.generate_json(
            tier=1,
            system_prompt=TIER1_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            images=None,
            fallback_generator=heuristic_fallback,
        )

        raw_json = call_result.parsed_json or {}
        raw_ids = raw_json.get("approved_item_ids") or []
        valid_ids: list[int] = []
        batch_id_set = {it.id for it in batch}
        for val in raw_ids:
            try:
                int_id = int(val)
                if int_id in batch_id_set and int_id not in valid_ids:
                    valid_ids.append(int_id)
            except (ValueError, TypeError):
                continue

        # Ensure deterministic safety if external LLM returned empty list on valid horology items
        if not valid_ids and batch:
            fb = heuristic_fallback()
            valid_ids = fb["approved_item_ids"]
            raw_json["triage_notes"] = fb["triage_notes"]

        valid_ids = valid_ids[:max_promotions]

        notes_dict = {
            str(k): str(v) for k, v in (raw_json.get("triage_notes") or {}).items()
        }
        return (
            Tier1BatchOutput(approved_item_ids=valid_ids, triage_notes=notes_dict),
            call_result,
        )
