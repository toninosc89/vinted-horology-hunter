from __future__ import annotations

import asyncio
import html
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote_plus

import httpx

from backend.agents.orchestrator import HorologyMASOrchestrator
from backend.database import (
    list_notification_logs,
    load_router_settings,
    load_scheduler_config,
    record_notification_log,
    save_scheduler_config,
    was_watch_already_notified,
)
from backend.schemas import (
    AlertSchedulerConfig,
    NotificationLogEntry,
    SchedulerStatusResponse,
    SearchRequest,
    WatchAppraisal,
)
from backend.vinted_client import VintedClient


class WatchAlertNotifier:
    """
    Dispatches real-time watch deal alerts to Telegram (Bot API with Photo + Inline Button)
    and WhatsApp (CallMeBot API, Custom Webhook/Gateway, + wa.me deep link).
    """

    @staticmethod
    def format_plain_alert(appraisal: WatchAppraisal) -> str:
        margin_sign = "+" if appraisal.net_margin_potential_eur >= 0 else ""
        roi_str = (
            f" ({margin_sign}{appraisal.roi_pct:.1f}%)"
            if appraisal.roi_pct is not None
            else ""
        )
        offer_str = (
            f"€{appraisal.suggested_offer_eur:.0f}"
            if appraisal.suggested_offer_eur
            else f"€{appraisal.price_listed_eur * 0.85:.0f}"
        )
        return (
            f"🚨 *AFFARE OROLOGIERO VINTED* (Score {appraisal.deal_score}/10)\n"
            f"⌚ *{appraisal.identified_brand_model}*\n"
            f"⚙️ Calibro/Ref: {appraisal.estimated_reference_caliber}\n"
            f"💰 Prezzo Vinted: *€{appraisal.price_listed_eur:.0f}* (Finito: €{appraisal.total_vinted_cost_eur:.2f})\n"
            f"📈 Valore Mercato: *€{appraisal.estimated_market_value_eur_min:.0f} - €{appraisal.estimated_market_value_eur_max:.0f}*\n"
            f"💵 Margine Netto: *{margin_sign}€{appraisal.net_margin_potential_eur:.0f}*{roi_str}\n"
            f"🎯 Azione: *{appraisal.recommended_action}* (Offerta: {offer_str})\n"
            f"🔗 Link Veloce Vinted:\n{appraisal.url}"
        )

    @staticmethod
    def format_telegram_html(appraisal: WatchAppraisal) -> str:
        margin_sign = "+" if appraisal.net_margin_potential_eur >= 0 else ""
        roi_str = (
            f" ({margin_sign}{appraisal.roi_pct:.1f}%)"
            if appraisal.roi_pct is not None
            else ""
        )
        offer_str = (
            f"€{appraisal.suggested_offer_eur:.0f}"
            if appraisal.suggested_offer_eur
            else f"€{appraisal.price_listed_eur * 0.85:.0f}"
        )
        model_esc = html.escape(appraisal.identified_brand_model)
        cal_esc = html.escape(appraisal.estimated_reference_caliber)
        url_esc = html.escape(appraisal.url)
        return (
            f"🚨 <b>AFFARE OROLOGIERO RILEVATO ({appraisal.deal_score}/10)</b>\n\n"
            f"⌚ <b>{model_esc}</b>\n"
            f"⚙️ <b>Calibro/Ref:</b> <code>{cal_esc}</code>\n"
            f"💰 <b>Prezzo Vinted:</b> €{appraisal.price_listed_eur:.0f} <i>(Finito: €{appraisal.total_vinted_cost_eur:.2f})</i>\n"
            f"📈 <b>Valore Mercato:</b> €{appraisal.estimated_market_value_eur_min:.0f} – €{appraisal.estimated_market_value_eur_max:.0f}\n"
            f"💵 <b>Margine Stimato:</b> <b>{margin_sign}€{appraisal.net_margin_potential_eur:.0f}{roi_str}</b>\n"
            f"🎯 <b>Azione:</b> {appraisal.recommended_action} • Offerta: <b>{offer_str}</b>\n\n"
            f"🔗 <a href=\"{url_esc}\">APRI SUBITO ANNUNCIO SU VINTED.IT</a>"
        )

    @staticmethod
    def build_whatsapp_deeplink(phone: str, text: str) -> str:
        clean_phone = re.sub(r"[^\d]", "", phone or "")
        encoded = quote_plus(text)
        if clean_phone:
            return f"https://wa.me/{clean_phone}?text={encoded}"
        return f"https://wa.me/?text={encoded}"

    @classmethod
    async def send_telegram(
        cls, bot_token: str, chat_id: str, appraisal: WatchAppraisal
    ) -> tuple[bool, str]:
        token = bot_token.strip()
        cid = chat_id.strip()
        if not token or not cid:
            return False, "Token Bot o Chat ID Telegram mancanti"

        caption_html = cls.format_telegram_html(appraisal)
        reply_markup = {
            "inline_keyboard": [
                [
                    {
                        "text": f"⌚ Apri su Vinted (€{appraisal.price_listed_eur:.0f})",
                        "url": appraisal.url,
                    }
                ]
            ]
        }

        async with httpx.AsyncClient(timeout=12.0) as client:
            if appraisal.photo_urls:
                photo_url = appraisal.photo_urls[0]
                try:
                    resp = await client.post(
                        f"https://api.telegram.org/bot{token}/sendPhoto",
                        json={
                            "chat_id": cid,
                            "photo": photo_url,
                            "caption": caption_html,
                            "parse_mode": "HTML",
                            "reply_markup": reply_markup,
                        },
                    )
                    if resp.status_code == 200 and resp.json().get("ok"):
                        return True, "Telegram (Foto + Link)"
                except Exception:
                    pass

            # Fallback to text message if photo upload fails
            try:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={
                        "chat_id": cid,
                        "text": caption_html,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": False,
                        "reply_markup": reply_markup,
                    },
                )
                data = resp.json() if resp.content else {}
                if resp.status_code == 200 and data.get("ok"):
                    return True, "Telegram (Messaggio + Link)"
                desc = data.get("description") or f"HTTP {resp.status_code}"
                return False, f"Errore Telegram: {desc}"
            except Exception as exc:
                return False, f"Errore rete Telegram: {str(exc)[:100]}"

    @classmethod
    async def send_whatsapp(
        cls,
        phone: str,
        apikey: str,
        webhook_url: str,
        appraisal: WatchAppraisal,
    ) -> tuple[bool, str]:
        text_msg = cls.format_plain_alert(appraisal)
        clean_phone = re.sub(r"[^\d+]", "", phone or "").strip()

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            # 1. Custom WhatsApp Webhook / Gateway if configured
            if webhook_url and webhook_url.strip().startswith("http"):
                try:
                    resp = await client.post(
                        webhook_url.strip(),
                        json={
                            "phone": clean_phone,
                            "text": text_msg,
                            "message": text_msg,
                            "url": appraisal.url,
                            "vinted_id": appraisal.vinted_id,
                            "deal_score": appraisal.deal_score,
                        },
                    )
                    if 200 <= resp.status_code < 300:
                        return True, "WhatsApp Webhook OK"
                    return False, f"WhatsApp Webhook HTTP {resp.status_code}"
                except Exception as exc:
                    return False, f"Errore WhatsApp Webhook: {str(exc)[:90]}"

            # 2. CallMeBot Free WhatsApp API (phone + apikey)
            if clean_phone and apikey and apikey.strip():
                try:
                    encoded_text = quote_plus(text_msg)
                    phone_digits = re.sub(r"[^\d]", "", clean_phone)
                    callmebot_url = (
                        f"https://api.callmebot.com/whatsapp.php"
                        f"?phone={phone_digits}&text={encoded_text}&apikey={quote_plus(apikey.strip())}"
                    )
                    resp = await client.get(callmebot_url)
                    body_lower = resp.text.lower()
                    if resp.status_code == 200 and (
                        "message queued" in body_lower
                        or "sent" in body_lower
                        or "whatsapp" in body_lower
                    ):
                        return True, "WhatsApp (CallMeBot API)"
                    return False, f"CallMeBot: {resp.text[:80].strip()}"
                except Exception as exc:
                    return False, f"Errore WhatsApp CallMeBot: {str(exc)[:90]}"

        if clean_phone:
            return True, "WhatsApp Link Rapido (wa.me pronto)"
        return False, "Configura Numero/API Key WhatsApp"

    @classmethod
    async def dispatch_alert(
        cls,
        config: AlertSchedulerConfig,
        appraisal: WatchAppraisal,
        db_path: Optional[Path] = None,
        record_in_db: bool = True,
    ) -> NotificationLogEntry:
        channels_attempted: list[str] = []
        status_parts: list[str] = []

        plain_text = cls.format_plain_alert(appraisal)
        wa_link = cls.build_whatsapp_deeplink(config.whatsapp_phone, plain_text)

        if config.telegram_enabled and config.telegram_bot_token and config.telegram_chat_id:
            ok_tg, msg_tg = await cls.send_telegram(
                config.telegram_bot_token, config.telegram_chat_id, appraisal
            )
            channels_attempted.append("Telegram")
            status_parts.append(f"{'✅' if ok_tg else '⚠️'} {msg_tg}")

        if config.whatsapp_enabled and (
            config.whatsapp_phone or config.whatsapp_webhook_url
        ):
            ok_wa, msg_wa = await cls.send_whatsapp(
                config.whatsapp_phone,
                config.whatsapp_apikey,
                config.whatsapp_webhook_url,
                appraisal,
            )
            channels_attempted.append("WhatsApp")
            status_parts.append(f"{'✅' if ok_wa else '⚠️'} {msg_wa}")

        if not channels_attempted:
            channels_attempted.append("Radar Dashboard")
            status_parts.append("✅ Salvato nel Radar Live (+ Link Veloce WhatsApp/Vinted)")

        channels_str = " + ".join(channels_attempted)
        status_str = " • ".join(status_parts)

        if record_in_db:
            return record_notification_log(
                appraisal=appraisal,
                channels_sent=channels_str,
                delivery_status=status_str,
                whatsapp_quick_link=wa_link,
                db_path=db_path,
            )

        return NotificationLogEntry(
            id=0,
            vinted_id=appraisal.vinted_id,
            title=appraisal.title,
            identified_brand_model=appraisal.identified_brand_model,
            price_listed_eur=appraisal.price_listed_eur,
            estimated_market_value_eur_min=appraisal.estimated_market_value_eur_min,
            estimated_market_value_eur_max=appraisal.estimated_market_value_eur_max,
            net_margin_potential_eur=appraisal.net_margin_potential_eur,
            deal_score=appraisal.deal_score,
            url=appraisal.url,
            photo_url=appraisal.photo_urls[0] if appraisal.photo_urls else "",
            channels_sent=channels_str,
            delivery_status=status_str,
            whatsapp_quick_link=wa_link,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )


class WatchRadarScheduler:
    """
    Background Asyncio Scheduler for On-Demand Recurring Vinted Watch Scans.
    Uses SQLite Tier 0 Cache so already-appraised watches cost €0.00 (0 tokens) on subsequent runs,
    and automatically notifies the user on Telegram/WhatsApp only for newly discovered deals.
    """

    def __init__(
        self,
        vinted_client: VintedClient,
        db_path: Optional[Path] = None,
    ) -> None:
        self.vinted_client = vinted_client
        self.db_path = db_path
        self.is_running_scan: bool = False
        self.last_run_at: Optional[str] = None
        self.next_run_epoch: Optional[float] = None
        self.total_runs: int = 0
        self.total_alerts_sent: int = 0
        self.last_run_items_found: int = 0
        self.last_run_new_alerts: int = 0
        self.last_run_cost_eur: float = 0.0
        self.last_error: str = ""
        self._task: Optional[asyncio.Task[None]] = None
        self._stopped: bool = False
        self._scan_lock: Optional[asyncio.Lock] = None
        self.latest_scan_items: list[WatchAppraisal] = []

    def _get_lock(self) -> asyncio.Lock:
        if self._scan_lock is None:
            self._scan_lock = asyncio.Lock()
        return self._scan_lock

    def start_background_loop(self) -> None:
        cfg = load_scheduler_config(db_path=self.db_path)
        if cfg.enabled:
            self.next_run_epoch = time.time() + (cfg.interval_minutes * 60)
        self._stopped = False
        try:
            loop = asyncio.get_running_loop()
            if self._task is None or self._task.done():
                self._task = loop.create_task(self._loop())
        except RuntimeError:
            pass

    async def stop_background_loop(self) -> None:
        self._stopped = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def update_config(self, new_config: AlertSchedulerConfig) -> AlertSchedulerConfig:
        saved = save_scheduler_config(new_config, db_path=self.db_path)
        if saved.enabled:
            self.next_run_epoch = time.time() + (saved.interval_minutes * 60)
        else:
            self.next_run_epoch = None
        return saved

    async def _loop(self) -> None:
        while not self._stopped:
            try:
                cfg = load_scheduler_config(db_path=self.db_path)
                if cfg.enabled and not self.is_running_scan:
                    now = time.time()
                    if self.next_run_epoch is None:
                        self.next_run_epoch = now + (cfg.interval_minutes * 60)
                    elif now >= self.next_run_epoch:
                        await self.execute_radar_cycle()
                        cfg_after = load_scheduler_config(db_path=self.db_path)
                        if cfg_after.enabled:
                            self.next_run_epoch = time.time() + (
                                cfg_after.interval_minutes * 60
                            )
                        else:
                            self.next_run_epoch = None
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.last_error = str(exc)[:160]
            await asyncio.sleep(2.0)

    async def execute_radar_cycle(self) -> dict[str, Any]:
        lock = self._get_lock()
        if lock.locked():
            return {"status": "already_running"}

        async with lock:
            self.is_running_scan = True
            self.last_error = ""
            cfg = load_scheduler_config(db_path=self.db_path)
            settings = load_router_settings(db_path=self.db_path)
            try:
                orchestrator = HorologyMASOrchestrator(
                    settings=settings,
                    vinted_client=self.vinted_client,
                    db_path=self.db_path,
                    enforce_stage2_jitter=False,
                )
                search_req = SearchRequest(
                    query=cfg.query,
                    max_price=cfg.max_price,
                    max_items=cfg.max_items,
                    sort_order="newest_first",
                    only_verified_working=cfg.only_verified_working,
                    bypass_cache=False,  # Crucial FinOps: €0.00 cost for watches already in SQLite cache!
                )
                res = await orchestrator.execute_search_pipeline(search_req)
                self.latest_scan_items = res.items
                self.total_runs += 1
                self.last_run_at = datetime.now().strftime("%H:%M:%S")
                self.last_run_items_found = len(res.items)
                self.last_run_cost_eur = res.telemetry.total_cost_eur

                new_alerts_count = 0
                sent_entries: list[NotificationLogEntry] = []

                for item in res.items:
                    if item.deal_score < cfg.min_deal_score:
                        continue
                    if cfg.only_verified_working and not item.is_working_verified:
                        continue
                    if item.franken_fake_risk == "HIGH":
                        continue
                    if was_watch_already_notified(
                        item.vinted_id, item.price_listed_eur, db_path=self.db_path
                    ):
                        continue

                    entry = await WatchAlertNotifier.dispatch_alert(
                        config=cfg,
                        appraisal=item,
                        db_path=self.db_path,
                        record_in_db=True,
                    )
                    sent_entries.append(entry)
                    new_alerts_count += 1
                    self.total_alerts_sent += 1

                self.last_run_new_alerts = new_alerts_count
                if cfg.enabled:
                    self.next_run_epoch = time.time() + (cfg.interval_minutes * 60)

                return {
                    "ok": True,
                    "items_found": len(res.items),
                    "new_alerts_sent": new_alerts_count,
                    "cost_eur": res.telemetry.total_cost_eur,
                    "items": [it.model_dump() for it in res.items],
                    "notifications": [e.model_dump() for e in sent_entries],
                }
            except Exception as exc:
                self.last_error = str(exc)[:180]
                return {"ok": False, "error": self.last_error}
            finally:
                self.is_running_scan = False

    def get_status(self) -> SchedulerStatusResponse:
        cfg = load_scheduler_config(db_path=self.db_path)
        secs_left: Optional[int] = None
        next_run_str: Optional[str] = None
        if cfg.enabled and self.next_run_epoch is not None:
            secs_left = max(0, int(round(self.next_run_epoch - time.time())))
            next_dt = datetime.now() + timedelta(seconds=secs_left)
            next_run_str = next_dt.strftime("%H:%M:%S")

        logs = list_notification_logs(limit=20, db_path=self.db_path)
        return SchedulerStatusResponse(
            config=cfg,
            is_running_scan=self.is_running_scan,
            last_run_at=self.last_run_at,
            next_run_at=next_run_str,
            seconds_until_next_run=secs_left,
            total_runs=self.total_runs,
            total_alerts_sent=self.total_alerts_sent or len(logs),
            last_run_items_found=self.last_run_items_found,
            last_run_new_alerts=self.last_run_new_alerts,
            last_run_cost_eur=self.last_run_cost_eur,
            last_error=self.last_error,
            recent_notifications=logs,
        )
