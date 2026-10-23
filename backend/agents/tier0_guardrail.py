from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from backend.database import get_cached_appraisal
from backend.schemas import CatalogItem, WatchAppraisal

# Mandatory Tier 0 Regex Blacklist + Italian/French/Spanish/English horology defect extensions
TIER0_BLACKLIST_PATTERN = re.compile(
    r"\b("
    r"non\s+funzionante|da\s+revisionare|per\s+ricambi|ricambi|fermo(?!\s+macchina)|rotto|rotta|"
    r"difettoso|difettosa|non\s+marciante|spares|repair|not\s+working|for\s+parts|"
    r"batteria\s+da\s+cambiare|pila\s+scarica|senza\s+batteria|solo\s+cassa|"
    r"solo\s+quadrante|blocco|lotto|"
    r"batteria\s+scarica|pila\s+da\s+cambiare|pila\s+da\s+sostituire|batteria\s+esaurita|"
    r"da\s+riparare|da\s+sistemare|non\s+funziona|non\s+parte|guasto|danneggiato|allagato|ossidato|"
    r"senza\s+corona|corona\s+staccata|bilanciere\s+rotto|molla\s+rotta|"
    r"non\s+testato|non\s+test[eé]|untested|hors\s+service|pour\s+pi[eè]ces|ne\s+fonctionne\s+pas|"
    r"pile\s+[aà]\s+changer|sans\s+pile"
    r")\b",
    re.IGNORECASE,
)

# Strict Watches-Only filter: rejects straps, spare links, empty boxes, wall clocks, and non-watch items
TIER0_NON_WATCH_PATTERN = re.compile(
    r"("
    r"^\s*(cinturino|cinturini|bracciale\s+cinturino|bracelet\s+de\s+montre|correa|scatola|bo[iî]te|estuche|maglia\s+bracciale)\b|"
    r"\b(solo\s+cinturino|cinturino\s+orologio|cinturino\s+per\s+orologio|cinturino\s+ricambio|"
    r"solo\s+scatola|scatola\s+vuota|scatola\s+orologio|scatola\s+porta|porta\s+orologi|portaorologi|"
    r"cofanetto\s+orologio|maglie\s+bracciale|maglia\s+di\s+ricambio|libretto\s+istruzioni|"
    r"orologio\s+da\s+parete|orologio\s+da\s+tavolo|sveglia\s+da\s+tavolo|"
    r"t-shirt|maglietta|felpa|pantaloni|jeans|scarpe|sneakers|giacca|cappotto|camicia|vestito|"
    r"gonna|borsa|zaino|occhiali|profumo|portafoglio|collana|orecchini|anello)\b"
    r")",
    re.IGNORECASE,
)

POOR_STATUS_TERMS = {"scarso", "poor", "non funzionante", "rotto"}
SATISFACTORY_STATUS_TERMS = {"satisfactory", "discreto", "accettabile"}
SATISFACTORY_DEFECT_HINTS = re.compile(
    r"\b(difetto|problema|ritarda\s+molto|anticipa\s+molto|si\s+ferma|graffi\s+profondi|crepa|ruggine|umidit[aà])\b",
    re.IGNORECASE,
)


class Tier0Guardrail:
    """
    TIER 0: Deterministic Guardrail & SQLite Cache (Cost: $0.00 - Local Python).
    Aggressively filters out non-working, broken, 'for parts/repair', water-damaged,
    'needs battery' watches, and non-watch items (straps, boxes, clothing) before spending a single LLM token.
    """

    @staticmethod
    def check_text_blacklist(
        title: str, status: str = "", description: str = ""
    ) -> tuple[bool, Optional[str]]:
        """
        Returns (is_valid, rejection_reason).
        If a non-watch item or blacklisted defect term is matched, returns (False, reason).
        """
        non_watch_match = TIER0_NON_WATCH_PATTERN.search(title)
        if non_watch_match:
            matched_item = non_watch_match.group(0).strip()
            return False, f"Tier 0 Non-Watch Filter: scartato accessorio/non-orologio '{matched_item}'"

        combined = f"{title} | {status} | {description}"
        match = TIER0_BLACKLIST_PATTERN.search(combined)
        if match:
            matched_term = match.group(0)
            return False, f"Tier 0 Regex Blacklist: rilevato termine '{matched_term}'"
        return True, None

    @staticmethod
    def check_condition_status(
        status: str, title: str = "", description: str = ""
    ) -> tuple[bool, Optional[str]]:
        """
        Rejects items whose Vinted status indicates broken/poor condition ('Scarso',
        or 'Satisfactory'/'Discreto' if accompanied by defect keywords).
        """
        norm_status = (status or "").strip().lower()
        if norm_status in POOR_STATUS_TERMS:
            return False, f"Tier 0 Condition Filter: stato Vinted '{status}' non ammesso"

        if norm_status in SATISFACTORY_STATUS_TERMS:
            combined = f"{title} {description}"
            if SATISFACTORY_DEFECT_HINTS.search(combined) or TIER0_BLACKLIST_PATTERN.search(combined):
                return (
                    False,
                    f"Tier 0 Condition Filter: stato '{status}' associato a difetti dichiarati",
                )
        return True, None

    @classmethod
    def inspect_catalog_item(
        cls,
        item: CatalogItem,
        bypass_cache: bool = False,
        db_path: Optional[Path] = None,
    ) -> tuple[bool, Optional[str], Optional[WatchAppraisal]]:
        """
        Runs full Tier 0 screening on a Stage 1 CatalogItem:
        1. Regex Blacklist on title, status, and description_snippet
        2. Condition Filter on status
        3. SQLite Cache lookup by (vinted_id, price)
        Returns (passed_tier0, rejection_reason, cached_appraisal).
        """
        ok_regex, reason_regex = cls.check_text_blacklist(
            item.title, item.status, item.description_snippet
        )
        if not ok_regex:
            return False, reason_regex, None

        ok_cond, reason_cond = cls.check_condition_status(
            item.status, item.title, item.description_snippet
        )
        if not ok_cond:
            return False, reason_cond, None

        if not bypass_cache:
            cached = get_cached_appraisal(item.id, item.price, db_path=db_path)
            if cached is not None:
                # Mark as retrieved from Tier 0 Cache with 0 new tokens spent
                cached_copy = cached.model_copy(
                    update={
                        "tier_reached": f"{cached.tier_reached} (Cache Tier 0)",
                        "tokens_used": 0,
                        "cost_usd": 0.0,
                    }
                )
                return True, None, cached_copy

        return True, None, None
