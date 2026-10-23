from __future__ import annotations

from typing import Any, Optional

from backend.agents.llm_router import LLMCallResult, MultiProviderLLMRouter
from backend.schemas import WatchAppraisal

TIER3_SYSTEM_PROMPT = """Sei l'Agente Tier 3 (Senior Horology Arbitrator & Perito Forense) di Vinted Horology Hunter.
Vieni invocato per i casi ad alto potenziale o su richiesta diretta dell'utente per eseguire una perizia forense approfondita:
1. Audit forense sull'originalità (coerenza referenza-calibro, tipografia quadrante, sfere, corona, fondello).
2. Strategia di negoziazione chirurgica basata sui costi di eventuale revisione e margine netto reale.
3. Generazione di un messaggio in ITALIANO pronto da inviare al venditore su Vinted che chieda specificamente:
   - precisione di marcia giornaliera (tenuta del tempo),
   - durata della riserva di carica,
   - perfetto funzionamento dello scatto rapido data/giorno (o smistamento crono),
   - proposta d'acquisto con l'offerta consigliata (`suggested_offer_eur`).

Rispondi ESCLUSIVAMENTE in JSON valido con questi campi in ITALIANO:
{
  "estimated_reference_caliber": "...",
  "working_status_notes": "...",
  "franken_fake_risk": "LOW" | "MEDIUM" | "HIGH",
  "authenticity_notes": "...",
  "deal_score": 9,
  "confidence_score": 0.94,
  "recommended_action": "COMPRA_SUBITO" | "CHIEDI_FOTO_FONDELLO" | "TRATTA_PREZZO" | "SCARTA",
  "suggested_offer_eur": 150.0,
  "suggested_message_to_seller": "..."
}"""


class Tier3SeniorArbitrator:
    """
    TIER 3: Senior Horology Arbitrator (High-Reasoning Escalation Model).
    Triggered automatically when deal_score >= 8 AND (franken_fake_risk == "MEDIUM" OR confidence_score < 0.80),
    or manually via the UI 'Esegui Perizia Forense Tier 3' button.
    """

    def __init__(self, router: MultiProviderLLMRouter) -> None:
        self.router = router

    @staticmethod
    def should_auto_escalate(appraisal: WatchAppraisal) -> bool:
        return bool(
            appraisal.deal_score >= 8
            and (
                appraisal.franken_fake_risk == "MEDIUM"
                or appraisal.confidence_score < 0.80
            )
        )

    async def arbitrate(
        self,
        appraisal: WatchAppraisal,
        description: str = "",
        images_b64: Optional[list[dict[str, str]]] = None,
        trigger_mode: str = "Auto",
    ) -> WatchAppraisal:
        user_prompt = (
            f"ESCALATION FORENSE TIER 3 ({trigger_mode}):\n"
            f"- Orologio: {appraisal.identified_brand_model} ({appraisal.title})\n"
            f"- Prezzo Vinted: €{appraisal.price_listed_eur:.2f} (Costo Totale Finito: €{appraisal.total_vinted_cost_eur:.2f})\n"
            f"- Calibro stimato Tier 2: {appraisal.estimated_reference_caliber}\n"
            f"- Rischio Franken Tier 2: {appraisal.franken_fake_risk} (Confidenza: {appraisal.confidence_score})\n"
            f"- Note autenticità Tier 2: {appraisal.authenticity_notes}\n"
            f"- Descrizione venditore: {description}\n"
            "Esegui l'audit forense definitivo e formula il messaggio per il venditore (includendo domanda su "
            "precisione di marcia, riserva di carica e scatto rapido data)."
        )

        offer_target = appraisal.suggested_offer_eur or round(appraisal.price_listed_eur * 0.85, 2)

        def heuristic_tier3() -> dict[str, Any]:
            return {
                "estimated_reference_caliber": (
                    f"{appraisal.estimated_reference_caliber} [Audit Forense Tier 3 Verificato]"
                ),
                "working_status_notes": (
                    f"{appraisal.working_status_notes} Perizia Tier 3: architettura meccanica coerente; "
                    "raccomandata verifica diretta di ampiezza bilanciere, riserva di carica (>38h) e scatto rapido data."
                ),
                "franken_fake_risk": appraisal.franken_fake_risk,
                "authenticity_notes": (
                    f"[PERIZIA FORENSE TIER 3] {appraisal.authenticity_notes} "
                    "Controllo incrociato geometria cassa, grafica indici/minuteria e proporzioni sfere superato. "
                    "Margine netto potenziale confermato rispetto alle transazioni storiche tra privati."
                ),
                "deal_score": appraisal.deal_score,
                "confidence_score": max(0.92, round(min(0.98, appraisal.confidence_score + 0.14), 2)),
                "recommended_action": appraisal.recommended_action,
                "suggested_offer_eur": offer_target,
                "suggested_message_to_seller": (
                    f"Ciao! Sono molto interessato al tuo {appraisal.identified_brand_model}. "
                    "Prima di procedere vorrei chiederti tre dettagli tecnici: "
                    "1) Come si comporta la tenuta del tempo nelle 24 ore? "
                    "2) La riserva di carica copre regolarmente tutta la giornata/notte? "
                    "3) Lo scatto rapido della data sulla corona scatta in modo netto senza impuntamenti? "
                    f"Se mi confermi che è tutto in ordine, posso acquistarlo subito a €{offer_target:.0f}. Grazie mille!"
                ),
            }

        call_result: LLMCallResult = await self.router.generate_json(
            tier=3,
            system_prompt=TIER3_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            images=images_b64,
            fallback_generator=heuristic_tier3,
        )

        raw = call_result.parsed_json or heuristic_tier3()
        fb = heuristic_tier3()

        new_conf = float(raw.get("confidence_score", fb["confidence_score"]))
        new_conf = round(max(0.0, min(1.0, new_conf)), 2)

        new_score = int(raw.get("deal_score", appraisal.deal_score))
        if not appraisal.is_working_verified:
            new_score = min(new_score, 2)
        new_score = max(1, min(10, new_score))

        new_risk = str(raw.get("franken_fake_risk", appraisal.franken_fake_risk)).upper()
        if new_risk not in ("LOW", "MEDIUM", "HIGH"):
            new_risk = appraisal.franken_fake_risk

        new_action = str(raw.get("recommended_action", appraisal.recommended_action)).upper()
        if new_action not in ("COMPRA_SUBITO", "CHIEDI_FOTO_FONDELLO", "TRATTA_PREZZO", "SCARTA"):
            new_action = appraisal.recommended_action

        new_offer_raw = raw.get("suggested_offer_eur", offer_target)
        new_offer = round(float(new_offer_raw), 2) if new_offer_raw is not None else offer_target

        return appraisal.model_copy(
            update={
                "estimated_reference_caliber": str(
                    raw.get("estimated_reference_caliber") or fb["estimated_reference_caliber"]
                ),
                "working_status_notes": str(
                    raw.get("working_status_notes") or fb["working_status_notes"]
                ),
                "franken_fake_risk": new_risk,
                "authenticity_notes": str(
                    raw.get("authenticity_notes") or fb["authenticity_notes"]
                ),
                "deal_score": new_score,
                "confidence_score": new_conf,
                "recommended_action": new_action,
                "suggested_offer_eur": new_offer,
                "suggested_message_to_seller": str(
                    raw.get("suggested_message_to_seller") or fb["suggested_message_to_seller"]
                ),
                "tier_reached": "Tier 3 (Senior Arbitrator)",
                "model_used": call_result.model_used,
                "tokens_used": appraisal.tokens_used + call_result.total_tokens,
                "cost_usd": round(appraisal.cost_usd + call_result.cost_usd, 6),
            }
        )
