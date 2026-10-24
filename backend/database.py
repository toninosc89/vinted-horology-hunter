from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

from backend.schemas import LLMRouterSettings, WatchAppraisal

load_dotenv()

DB_PATH = Path(__file__).resolve().parent / "horology_hunter.db"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    target = db_path or DB_PATH
    conn = sqlite3.connect(str(target), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS appraisal_cache (
                    vinted_id INTEGER NOT NULL,
                    price_listed_eur REAL NOT NULL,
                    appraisal_json TEXT NOT NULL,
                    description_text TEXT DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (vinted_id, price_listed_eur)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reference_valuations (
                    ref_key TEXT PRIMARY KEY,
                    canonical_model TEXT NOT NULL,
                    canonical_caliber TEXT NOT NULL,
                    market_min_eur REAL NOT NULL,
                    market_max_eur REAL NOT NULL,
                    sample_count INTEGER DEFAULT 1,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS router_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    settings_json TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
    finally:
        conn.close()


def extract_canonical_reference_key(
    appraisal: WatchAppraisal, description_text: str = ""
) -> Optional[str]:
    """
    Extracts a deterministic canonical reference key for a watch so that duplicate listings
    or multiple listings of the exact same reference (e.g., Seiko 5Y30-5060, Orient Star RE-AU0006S00B)
    always share the exact same secondary-market valuation (estimated_market_value_eur_min / max).
    """
    blob = f"{appraisal.estimated_reference_caliber} {appraisal.identified_brand_model} {appraisal.title} {description_text}"
    work_flag = 1 if appraisal.is_working_verified else 0
    risk_flag = appraisal.franken_fake_risk

    # 1. Orient / Orient Star modern references (normalize regional suffix 00B/00D -> base reference)
    orient_match = re.search(
        r"\b((?:RE|RA)-[A-Z0-9]{6}|SAF\d{4}[A-Z]|SDK\d{4}[A-Z]|WZ\d{4}[A-Z]{2}|CEW\d{4}[A-Z]|\d{6}-\d{2})[A-Z0-9]*\b",
        blob,
        re.IGNORECASE,
    )
    if orient_match:
        code = orient_match.group(1).upper()
        return f"REF:{code}|W:{work_flag}|R:{risk_flag}"

    # 2. Seiko / Citizen hyphenated caliber-case reference codes (e.g. 5Y30-5060, 6139-6002, 7009-3040)
    for m in re.finditer(r"\b([0-9A-Z]{4})-([0-9A-Z]{4,6})\b", blob, re.IGNORECASE):
        p1, p2 = m.group(1).upper(), m.group(2).upper()
        # Exclude year ranges like 1970-1980 or 1980-1990
        if p1.isdigit() and p2.isdigit() and 1950 <= int(p1) <= 2030 and 1950 <= int(p2) <= 2030:
            continue
        if sum(ch.isdigit() for ch in p1) >= 2 and sum(ch.isdigit() for ch in p2) >= 3:
            return f"REF:{p1}-{p2[:4]}|W:{work_flag}|R:{risk_flag}"

    # 3. Citizen Promaster / Seiko modern reference codes (e.g. NY0040, BN0151, BN0235, SKX007, SND367, SGEG05)
    modern_match = re.search(
        r"\b(NY\d{4}|BN\d{4}|JP\d{4}|SKX\d{3}|SND\d{3}|SGEG\d{2})\b",
        blob,
        re.IGNORECASE,
    )
    if modern_match:
        code = modern_match.group(1).upper()
        return f"REF:{code}|W:{work_flag}|R:{risk_flag}"

    # 4. Duplicate listing fingerprint (identical title + seller description or shared image hash)
    norm_desc = re.sub(r"\W+", "", (description_text or "").lower())
    norm_title = re.sub(r"\W+", "", (appraisal.title or "").lower())
    if len(norm_desc) >= 25:
        fp = hashlib.sha1(f"{norm_title}:{norm_desc[:120]}".encode("utf-8")).hexdigest()[:12]
        return f"DUP:{fp}|W:{work_flag}|R:{risk_flag}"

    return None


def compute_deterministic_deal_score(
    net_margin_eur: float,
    total_cost_eur: float,
    is_working_verified: bool,
    franken_fake_risk: str,
    confidence_score: float,
) -> tuple[int, float, str]:
    """
    Calculates a deterministic Deal Score (1..10), ROI %, and Recommended Action
    strictly anchored to the real net margin potential, ROI %, working status, and franken risk.
    """
    cost_base = max(total_cost_eur, 1.0)
    roi_pct = round((net_margin_eur / cost_base) * 100.0, 1)

    if not is_working_verified:
        return 1, roi_pct, "SCARTA"
    if franken_fake_risk == "HIGH":
        return 2, roi_pct, "SCARTA"

    if roi_pct >= 55.0 and net_margin_eur >= 50.0:
        score = 10
    elif (roi_pct >= 32.0 and net_margin_eur >= 25.0) or net_margin_eur >= 70.0:
        score = 9
    elif (roi_pct >= 15.0 and net_margin_eur >= 12.0) or net_margin_eur >= 35.0:
        score = 8
    elif net_margin_eur >= 0.0:
        score = 7
    elif roi_pct >= -26.0 or net_margin_eur >= -45.0:
        score = 6
    elif roi_pct >= -40.0 or net_margin_eur >= -95.0:
        score = 5
    elif roi_pct >= -55.0:
        score = 4
    else:
        score = 3

    if franken_fake_risk == "MEDIUM":
        score = min(score, 8)

    if score <= 4:
        action = "SCARTA"
    elif franken_fake_risk == "MEDIUM" or confidence_score < 0.80:
        action = "CHIEDI_FOTO_FONDELLO"
    elif score >= 9 and net_margin_eur >= 25.0:
        action = "COMPRA_SUBITO"
    else:
        action = "TRATTA_PREZZO"

    return score, roi_pct, action


def apply_canonical_valuation(
    appraisal: WatchAppraisal,
    description_text: str = "",
    db_path: Optional[Path] = None,
) -> WatchAppraisal:
    """
    Ensures `appraisal` uses the canonical market value (min/max EUR) registered for its
    watch reference or duplicate-listing fingerprint, recalculates `net_margin_potential_eur`,
    deterministic `deal_score`, `roi_pct`, and sets `is_best_price_for_ref`.
    """
    ref_key = extract_canonical_reference_key(appraisal, description_text)

    init_db(db_path)
    conn = get_connection(db_path)
    try:
        canon_min = float(appraisal.estimated_market_value_eur_min)
        canon_max = float(appraisal.estimated_market_value_eur_max)
        canon_model = appraisal.identified_brand_model
        canon_caliber = appraisal.estimated_reference_caliber
        sample_count = 1

        is_tier3_grounded = "Google Search" in (appraisal.model_used or "") or (
            "Tier 3" in (appraisal.tier_reached or "")
        )

        if ref_key:
            row = conn.execute(
                """
                SELECT canonical_model, canonical_caliber, market_min_eur, market_max_eur, sample_count
                FROM reference_valuations
                WHERE ref_key = ?
                """,
                (ref_key,),
            ).fetchone()

            if is_tier3_grounded:
                # Tier 3 Senior Arbitrator with Live Market Check is authoritative: update reference_valuations
                sample_count = int(row["sample_count"] or 1) if row is not None else 1
                with conn:
                    conn.execute(
                        """
                        INSERT INTO reference_valuations
                            (ref_key, canonical_model, canonical_caliber, market_min_eur, market_max_eur, sample_count, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(ref_key) DO UPDATE SET
                            canonical_model = excluded.canonical_model,
                            canonical_caliber = excluded.canonical_caliber,
                            market_min_eur = excluded.market_min_eur,
                            market_max_eur = excluded.market_max_eur,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (
                            ref_key,
                            canon_model,
                            canon_caliber,
                            canon_min,
                            canon_max,
                            sample_count,
                        ),
                    )
            elif row is not None:
                canon_min = float(row["market_min_eur"])
                canon_max = float(row["market_max_eur"])
                sample_count = int(row["sample_count"] or 1)
                if sample_count > 1 or ref_key.startswith("DUP:"):
                    canon_model = row["canonical_model"]
                    canon_caliber = row["canonical_caliber"]
            else:
                with conn:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO reference_valuations
                            (ref_key, canonical_model, canonical_caliber, market_min_eur, market_max_eur, sample_count)
                        VALUES (?, ?, ?, ?, ?, 1)
                        """,
                        (
                            ref_key,
                            canon_model,
                            canon_caliber,
                            canon_min,
                            canon_max,
                        ),
                    )

        avg_market = (canon_min + canon_max) / 2.0
        new_margin = round(avg_market - appraisal.total_vinted_cost_eur, 2)
        det_score, roi_pct, det_action = compute_deterministic_deal_score(
            net_margin_eur=new_margin,
            total_cost_eur=appraisal.total_vinted_cost_eur,
            is_working_verified=appraisal.is_working_verified,
            franken_fake_risk=appraisal.franken_fake_risk,
            confidence_score=appraisal.confidence_score,
        )

        # Ensure suggested_offer_eur guarantees a positive deal when negotiable
        suggested_offer = appraisal.suggested_offer_eur
        if appraisal.is_working_verified and appraisal.franken_fake_risk != "HIGH":
            target_offer = round(min(appraisal.price_listed_eur * 0.88, avg_market * 0.82), 2)
            if suggested_offer is None or suggested_offer > appraisal.price_listed_eur:
                suggested_offer = target_offer

        return appraisal.model_copy(
            update={
                "identified_brand_model": canon_model,
                "estimated_reference_caliber": canon_caliber,
                "estimated_market_value_eur_min": canon_min,
                "estimated_market_value_eur_max": canon_max,
                "net_margin_potential_eur": new_margin,
                "deal_score": det_score,
                "recommended_action": det_action,  # type: ignore
                "suggested_offer_eur": suggested_offer,
                "canonical_ref_key": ref_key.split("|")[0] if ref_key else None,
                "roi_pct": roi_pct,
                "ref_listings_count": max(sample_count, appraisal.ref_listings_count),
            }
        )
    finally:
        conn.close()


def reconcile_all_cached_appraisals(db_path: Optional[Path] = None) -> int:
    """
    Scans `appraisal_cache`, groups items that share the same canonical watch reference or
    duplicate-listing fingerprint, computes a single consensus market valuation (prioritizing
    Tier 3 Web-Search-verified valuations), determines the lowest price on Vinted for each
    reference (`is_best_price_for_ref`), flags duplicate seller reposts (`is_duplicate_repost`),
    and updates `appraisal_cache`.
    """
    init_db(db_path)
    conn = get_connection(db_path)
    updated_count = 0
    try:
        rows = conn.execute(
            "SELECT vinted_id, price_listed_eur, appraisal_json, description_text FROM appraisal_cache"
        ).fetchall()

        parsed_rows: list[tuple[int, float, WatchAppraisal, str, Optional[str], str]] = []
        groups: dict[str, list[WatchAppraisal]] = {}
        dup_groups: dict[str, list[int]] = {}

        for r in rows:
            try:
                app = WatchAppraisal.model_validate(json.loads(r["appraisal_json"]))
            except Exception:
                continue
            desc = r["description_text"] or ""
            rkey = extract_canonical_reference_key(app, desc)
            norm_desc = re.sub(r"\W+", "", desc.lower())[:100]
            norm_title = re.sub(r"\W+", "", (app.title or "").lower())
            dup_fp = f"{norm_title}:{int(round(app.price_listed_eur))}:{norm_desc}" if len(norm_desc) >= 20 else ""
            if dup_fp:
                dup_groups.setdefault(dup_fp, []).append(int(r["vinted_id"]))
            parsed_rows.append((int(r["vinted_id"]), float(r["price_listed_eur"]), app, desc, rkey, dup_fp))
            if rkey:
                groups.setdefault(rkey, []).append(app)

        # Compute consensus valuation & lowest listing price per canonical reference key
        consensus_map: dict[str, tuple[str, str, float, float, float, int]] = {}
        for rkey, app_list in groups.items():
            # Prioritize Tier 3 Web-Comps / Search-grounded valuations if present
            grounded_samples = [
                a
                for a in app_list
                if "Google Search" in (a.model_used or "")
                or "Web Comps" in (a.model_used or "")
                or "Tier 3" in (a.tier_reached or "")
            ]
            val_samples = grounded_samples if grounded_samples else app_list

            avg_min = sum(a.estimated_market_value_eur_min for a in val_samples) / len(val_samples)
            avg_max = sum(a.estimated_market_value_eur_max for a in val_samples) / len(val_samples)
            canon_min = round(avg_min / 5.0) * 5.0 if avg_min >= 20 else round(avg_min, 2)
            canon_max = round(avg_max / 5.0) * 5.0 if avg_max >= 20 else round(avg_max, 2)
            if canon_max <= canon_min:
                canon_max = canon_min + 25.0

            lowest_price = min(a.price_listed_eur for a in app_list)
            cheapest_candidates = [a for a in app_list if abs(a.price_listed_eur - lowest_price) < 0.01]
            best_price_vid = min(a.vinted_id for a in cheapest_candidates)

            best_app = max(
                val_samples,
                key=lambda a: (
                    1
                    if (
                        "Google Search" in (a.model_used or "")
                        or "Web Comps" in (a.model_used or "")
                        or "Tier 3" in (a.tier_reached or "")
                    )
                    else 0,
                    a.confidence_score,
                    len(a.estimated_reference_caliber),
                ),
            )
            consensus_map[rkey] = (
                best_app.identified_brand_model,
                best_app.estimated_reference_caliber,
                float(canon_min),
                float(canon_max),
                float(lowest_price),
                int(best_price_vid),
            )

        with conn:
            for rkey, (c_model, c_cal, c_min, c_max, _, _) in consensus_map.items():
                conn.execute(
                    """
                    INSERT INTO reference_valuations
                        (ref_key, canonical_model, canonical_caliber, market_min_eur, market_max_eur, sample_count, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(ref_key) DO UPDATE SET
                        canonical_model = excluded.canonical_model,
                        canonical_caliber = excluded.canonical_caliber,
                        market_min_eur = excluded.market_min_eur,
                        market_max_eur = excluded.market_max_eur,
                        sample_count = excluded.sample_count,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (rkey, c_model, c_cal, c_min, c_max, len(groups[rkey])),
                )

            for vid, price_eur, app, desc, rkey, dup_fp in parsed_rows:
                if rkey and rkey in consensus_map:
                    c_model, c_cal, c_min, c_max, lowest_p, best_vid = consensus_map[rkey]
                    grp_count = len(groups[rkey])
                    is_best = bool(grp_count > 1 and vid == best_vid)
                    ref_short = rkey.split("|")[0]
                else:
                    c_model = app.identified_brand_model
                    c_cal = app.estimated_reference_caliber
                    c_min = app.estimated_market_value_eur_min
                    c_max = app.estimated_market_value_eur_max
                    lowest_p = app.price_listed_eur
                    grp_count = 1
                    is_best = False
                    ref_short = None

                is_dup = bool(dup_fp and len(dup_groups.get(dup_fp, [])) > 1 and vid != min(dup_groups[dup_fp]))

                avg_mkt = (c_min + c_max) / 2.0
                new_margin = round(avg_mkt - app.total_vinted_cost_eur, 2)
                det_score, roi_pct, det_action = compute_deterministic_deal_score(
                    net_margin_eur=new_margin,
                    total_cost_eur=app.total_vinted_cost_eur,
                    is_working_verified=app.is_working_verified,
                    franken_fake_risk=app.franken_fake_risk,
                    confidence_score=app.confidence_score,
                )

                updated_app = app.model_copy(
                    update={
                        "identified_brand_model": c_model if grp_count > 1 else app.identified_brand_model,
                        "estimated_reference_caliber": c_cal if grp_count > 1 else app.estimated_reference_caliber,
                        "estimated_market_value_eur_min": c_min,
                        "estimated_market_value_eur_max": c_max,
                        "net_margin_potential_eur": new_margin,
                        "deal_score": det_score,
                        "recommended_action": det_action,  # type: ignore
                        "canonical_ref_key": ref_short,
                        "roi_pct": roi_pct,
                        "is_best_price_for_ref": is_best,
                        "ref_listings_count": grp_count,
                        "ref_lowest_price_eur": lowest_p if grp_count > 1 else None,
                        "is_duplicate_repost": is_dup,
                    }
                )
                if updated_app.model_dump() != app.model_dump():
                    conn.execute(
                        """
                        UPDATE appraisal_cache
                        SET appraisal_json = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE vinted_id = ? AND ABS(price_listed_eur - ?) < 0.01
                        """,
                        (updated_app.model_dump_json(), vid, price_eur),
                    )
                    updated_count += 1
        return updated_count
    finally:
        conn.close()


def list_cached_appraisals(
    limit: int = 36, db_path: Optional[Path] = None
) -> list[WatchAppraisal]:
    """
    Returns up to `limit` cached watch appraisals from SQLite at $0.00 / €0.00 (0 tokens),
    sorted by deal_score descending and net_margin_potential_eur descending.
    Used on initial frontend load so refreshing the browser never triggers a paid LLM scan automatically.
    """
    init_db(db_path)
    reconcile_all_cached_appraisals(db_path=db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT appraisal_json FROM appraisal_cache
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (max(1, limit * 2),),
        ).fetchall()
        seen_ids: set[int] = set()
        results: list[WatchAppraisal] = []
        for r in rows:
            try:
                app = WatchAppraisal.model_validate(json.loads(r["appraisal_json"]))
                if app.vinted_id in seen_ids:
                    continue
                seen_ids.add(app.vinted_id)
                results.append(
                    app.model_copy(
                        update={
                            "tier_reached": (
                                app.tier_reached
                                if "Cache" in app.tier_reached
                                else f"{app.tier_reached} • Cache SQLite"
                            ),
                            "tokens_used": 0,
                            "cost_usd": 0.0,
                        }
                    )
                )
            except Exception:
                continue
        results.sort(
            key=lambda a: (a.deal_score, a.net_margin_potential_eur),
            reverse=True,
        )
        return results[:limit]
    finally:
        conn.close()


def get_cached_appraisal(
    vinted_id: int,
    price_listed_eur: Optional[float] = None,
    db_path: Optional[Path] = None,
) -> Optional[WatchAppraisal]:
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        if price_listed_eur is not None:
            row = conn.execute(
                """
                SELECT appraisal_json, description_text FROM appraisal_cache
                WHERE vinted_id = ? AND ABS(price_listed_eur - ?) < 0.01
                """,
                (vinted_id, float(price_listed_eur)),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT appraisal_json, description_text FROM appraisal_cache
                WHERE vinted_id = ?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (vinted_id,),
            ).fetchone()

        if not row:
            return None
        data = json.loads(row["appraisal_json"])
        appraisal = WatchAppraisal.model_validate(data)
        return apply_canonical_valuation(
            appraisal, description_text=row["description_text"] or "", db_path=db_path
        )
    except Exception:
        return None
    finally:
        conn.close()


def get_cached_description(
    vinted_id: int, db_path: Optional[Path] = None
) -> str:
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            """
            SELECT description_text FROM appraisal_cache
            WHERE vinted_id = ?
            ORDER BY updated_at DESC LIMIT 1
            """,
            (vinted_id,),
        ).fetchone()
        return row["description_text"] if row and row["description_text"] else ""
    finally:
        conn.close()


def save_cached_appraisal(
    appraisal: WatchAppraisal,
    description_text: str = "",
    db_path: Optional[Path] = None,
) -> WatchAppraisal:
    init_db(db_path)
    normalized = apply_canonical_valuation(
        appraisal, description_text=description_text, db_path=db_path
    )
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO appraisal_cache (vinted_id, price_listed_eur, appraisal_json, description_text, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(vinted_id, price_listed_eur) DO UPDATE SET
                    appraisal_json = excluded.appraisal_json,
                    description_text = CASE WHEN excluded.description_text != '' THEN excluded.description_text ELSE appraisal_cache.description_text END,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    normalized.vinted_id,
                    float(normalized.price_listed_eur),
                    normalized.model_dump_json(),
                    description_text,
                ),
            )
        return normalized
    finally:
        conn.close()


def clear_appraisal_cache(db_path: Optional[Path] = None) -> int:
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM reference_valuations")
            cursor = conn.execute("DELETE FROM appraisal_cache")
            return cursor.rowcount
    finally:
        conn.close()


def clear_heuristic_only_cache(db_path: Optional[Path] = None) -> int:
    """
    Removes only fallback/heuristic entries from `appraisal_cache`, preserving all
    paid LLM appraisals so changing settings never forces costly re-evaluations.
    """
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.execute(
                "DELETE FROM appraisal_cache WHERE appraisal_json LIKE '%heuristic%'"
            )
            return cursor.rowcount
    finally:
        conn.close()


def load_router_settings(db_path: Optional[Path] = None) -> LLMRouterSettings:
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT settings_json FROM router_settings WHERE id = 1"
        ).fetchone()
        if row:
            saved = LLMRouterSettings.model_validate(json.loads(row["settings_json"]))
            # FinOps Auto-Upgrade: migrate legacy expensive Tier 2 Gemini 3 Flash ($0.50/$3.00)
            # to Gemini 3.1 Flash Lite ($0.10/$0.40) when auto_optimize_enabled is True
            if (
                saved.auto_optimize_enabled
                and saved.tier2_provider == "gemini"
                and saved.tier2_model == "gemini-3-flash-preview"
            ):
                saved.tier2_model = "gemini-3.1-flash-lite-preview"
                with conn:
                    conn.execute(
                        "UPDATE router_settings SET settings_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                        (saved.model_dump_json(),),
                    )
        else:
            saved = LLMRouterSettings()

        # Merge with environment variables if UI values are empty
        if not saved.gemini_api_key and os.getenv("GEMINI_API_KEY"):
            saved.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        if not saved.openai_api_key and os.getenv("OPENAI_API_KEY"):
            saved.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        if not saved.anthropic_api_key and os.getenv("ANTHROPIC_API_KEY"):
            saved.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not saved.groq_api_key and os.getenv("GROQ_API_KEY"):
            saved.groq_api_key = os.getenv("GROQ_API_KEY", "")
        if not saved.deepseek_api_key and os.getenv("DEEPSEEK_API_KEY"):
            saved.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not saved.openrouter_api_key and os.getenv("OPENROUTER_API_KEY"):
            saved.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        if os.getenv("OLLAMA_BASE_URL"):
            saved.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

        return saved
    finally:
        conn.close()


def save_router_settings(
    settings: LLMRouterSettings, db_path: Optional[Path] = None
) -> LLMRouterSettings:
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO router_settings (id, settings_json, updated_at)
                VALUES (1, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    settings_json = excluded.settings_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (settings.model_dump_json(),),
            )
        return settings
    finally:
        conn.close()
