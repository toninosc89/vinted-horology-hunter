import React, { useState, useEffect } from 'react'
import {
  Bell,
  Clock,
  Play,
  Square,
  Zap,
  Send,
  ExternalLink,
  MessageCircle,
  CheckCircle2,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Radio,
} from 'lucide-react'

const INTERVAL_PRESETS = [5, 10, 15, 30, 60]

export default function RadarSchedulerPanel({
  currentSearchQuery,
  currentMaxPrice,
  onRadarItemsFound,
}) {
  const [status, setStatus] = useState({
    config: {
      enabled: false,
      query: 'Seiko Vintage',
      max_price: 350,
      max_items: 10,
      interval_minutes: 15,
      min_deal_score: 7,
      only_verified_working: true,
      telegram_enabled: false,
      telegram_bot_token: '',
      telegram_chat_id: '',
      whatsapp_enabled: false,
      whatsapp_phone: '',
      whatsapp_apikey: '',
      whatsapp_webhook_url: '',
    },
    is_running_scan: false,
    last_run_at: null,
    next_run_at: null,
    seconds_until_next_run: null,
    total_runs: 0,
    total_alerts_sent: 0,
    last_run_items_found: 0,
    last_run_new_alerts: 0,
    last_run_cost_eur: 0.0,
    last_error: '',
    recent_notifications: [],
  })

  const [form, setForm] = useState(status.config)
  const [expanded, setExpanded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState(null)
  const [countdown, setCountdown] = useState(null)

  const fetchSchedulerStatus = async (syncForm = false) => {
    try {
      const resp = await fetch('/api/scheduler/status')
      if (!resp.ok) return
      const data = await resp.json()
      setStatus(data)
      setCountdown(data.seconds_until_next_run)
      if (syncForm && data.config) {
        setForm(data.config)
      }
    } catch {
      // ignore offline
    }
  }

  useEffect(() => {
    fetchSchedulerStatus(true)
    const poll = setInterval(() => {
      fetchSchedulerStatus(false)
    }, 6000)
    return () => clearInterval(poll)
  }, [])

  useEffect(() => {
    if (!status.config?.enabled || countdown === null) return
    const timer = setInterval(() => {
      setCountdown((prev) => (prev !== null && prev > 0 ? prev - 1 : 0))
    }, 1000)
    return () => clearInterval(timer)
  }, [status.config?.enabled, countdown])

  const formatCountdown = (secs) => {
    if (secs === null || secs === undefined) return '--:--'
    const m = Math.floor(secs / 60)
    const s = secs % 60
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }

  const updateField = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const handleSyncFromSearchBar = () => {
    setForm((prev) => ({
      ...prev,
      query: currentSearchQuery || prev.query,
      max_price: Number(currentMaxPrice) || prev.max_price,
    }))
    setFeedback({
      ok: true,
      text: `Parametri copiati dalla barra di ricerca: "${currentSearchQuery}" (Max €${currentMaxPrice})`,
    })
  }

  const saveConfigToServer = async (nextConfig, msgText) => {
    setBusy(true)
    setFeedback(null)
    try {
      const resp = await fetch('/api/scheduler/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(nextConfig),
      })
      if (!resp.ok) throw new Error('Errore salvataggio configurazione Radar')
      const data = await resp.json()
      setStatus(data)
      setForm(data.config)
      setCountdown(data.seconds_until_next_run)
      if (msgText) {
        setFeedback({ ok: true, text: msgText })
      }
    } catch (err) {
      setFeedback({ ok: false, text: err.message })
    } finally {
      setBusy(false)
    }
  }

  const handleToggleRadar = async () => {
    const nextEnabled = !form.enabled
    const nextConfig = {
      ...form,
      enabled: nextEnabled,
      interval_minutes: Math.max(1, Number(form.interval_minutes) || 15),
      max_price: Number(form.max_price) || 350,
      min_deal_score: Number(form.min_deal_score) || 7,
    }
    await saveConfigToServer(
      nextConfig,
      nextEnabled
        ? `Radar Automatico ATTIVATO: scansione "${nextConfig.query}" ogni ${nextConfig.interval_minutes} minuti!`
        : 'Radar Automatico messo in pausa.'
    )
  }

  const handleRunRadarNow = async () => {
    setBusy(true)
    setFeedback({
      ok: true,
      text: `Scansione Radar in corso per "${form.query}"...`,
    })
    try {
      const payload = {
        ...form,
        interval_minutes: Math.max(1, Number(form.interval_minutes) || 15),
        max_price: Number(form.max_price) || 350,
        min_deal_score: Number(form.min_deal_score) || 7,
      }
      const resp = await fetch('/api/scheduler/run-now', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!resp.ok) throw new Error('Errore durante il giro Radar')
      const data = await resp.json()
      if (data.status) {
        setStatus(data.status)
        setCountdown(data.status.seconds_until_next_run)
      }
      if (data.cycle?.items && onRadarItemsFound) {
        onRadarItemsFound(data.cycle.items)
      }
      const alertsCount = data.cycle?.new_alerts_sent || 0
      const foundCount = data.cycle?.items_found || 0
      setFeedback({
        ok: true,
        text: `Giro Radar completato: ${foundCount} orologi analizzati, ${alertsCount} nuovi alert inviati (Costo: €${Number(
          data.cycle?.cost_eur || 0
        ).toFixed(4)})!`,
      })
      if (alertsCount > 0) {
        setExpanded(true)
      }
    } catch (err) {
      setFeedback({ ok: false, text: err.message })
    } finally {
      setBusy(false)
    }
  }

  const handleSendTestAlert = async () => {
    setBusy(true)
    setFeedback({
      ok: true,
      text: 'Invio notifica di prova a Telegram / WhatsApp in corso...',
    })
    try {
      const resp = await fetch('/api/scheduler/test-alert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      if (!resp.ok) throw new Error('Impossibile inviare alert di prova')
      const data = await resp.json()
      if (data.status) {
        setStatus(data.status)
      }
      setFeedback({
        ok: true,
        text: `Alert di prova generato: ${data.entry?.delivery_status || 'OK'}`,
      })
    } catch (err) {
      setFeedback({ ok: false, text: err.message })
    } finally {
      setBusy(false)
    }
  }

  const isRunning = status.config?.enabled

  return (
    <section
      data-testid="radar-scheduler-panel"
      className={`rounded-2xl border p-4 sm:p-5 shadow-xl transition-all ${
        isRunning
          ? 'bg-gradient-to-r from-[#0d1f1d] via-[#111c2d] to-[#13221f] border-emerald-500/50'
          : 'bg-gradient-to-r from-[#111827] via-[#131c2e] to-[#111827] border-sky-500/30'
      }`}
    >
      {/* Top Bar: Controls & Live Status */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div className="flex items-start sm:items-center gap-3">
          <div
            className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 border ${
              isRunning
                ? 'bg-emerald-500/20 border-emerald-400/50 text-emerald-300'
                : 'bg-sky-500/15 border-sky-500/30 text-sky-300'
            }`}
          >
            <Radio className={`w-5 h-5 ${isRunning ? 'animate-pulse' : ''}`} />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-extrabold text-white">
                Radar Scansione Periodica On-Demand & Alert WhatsApp / Telegram
              </h2>
              {isRunning ? (
                <span className="px-2.5 py-0.5 text-[10px] font-extrabold uppercase rounded-full bg-emerald-500/25 text-emerald-200 border border-emerald-400/40 flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                  ATTIVO • Ogni {status.config.interval_minutes} min (Prossimo tra{' '}
                  {formatCountdown(countdown)})
                </span>
              ) : (
                <span className="px-2 py-0.5 text-[10px] font-bold uppercase rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                  In Pausa • Attivabile On-Demand
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Pianifica una scansione automatica ogni N minuti: usa la Cache SQLite (€0,00 sugli orologi già visti) e ti avvisa su Telegram o WhatsApp appena esce un vero affare con il link veloce a Vinted.
            </p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <button
            type="button"
            disabled={busy || status.is_running_scan}
            onClick={handleToggleRadar}
            data-testid="toggle-radar-btn"
            className={`px-4 py-2 rounded-xl font-extrabold text-xs flex items-center gap-1.5 shadow-lg transition ${
              isRunning
                ? 'bg-rose-600 hover:bg-rose-500 text-white'
                : 'bg-emerald-500 hover:bg-emerald-400 text-slate-950'
            }`}
          >
            {isRunning ? (
              <>
                <Square className="w-3.5 h-3.5 fill-current" />
                <span>Ferma Scansione Periodica</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Attiva Ogni {form.interval_minutes} Min</span>
              </>
            )}
          </button>

          <button
            type="button"
            disabled={busy || status.is_running_scan}
            onClick={handleRunRadarNow}
            data-testid="run-radar-now-btn"
            className="px-3.5 py-2 rounded-xl bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-200 font-bold text-xs flex items-center gap-1.5 transition"
          >
            {status.is_running_scan || busy ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Radar in corso...</span>
              </>
            ) : (
              <>
                <Zap className="w-3.5 h-3.5 text-amber-400" />
                <span>Esegui Giro Ora</span>
              </>
            )}
          </button>

          <button
            type="button"
            onClick={() => setExpanded((prev) => !prev)}
            data-testid="expand-radar-settings-btn"
            className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 font-semibold text-xs flex items-center gap-1.5 transition"
          >
            <Bell className="w-3.5 h-3.5 text-sky-400" />
            <span>
              Canali & Log Alert ({status.recent_notifications?.length || 0})
            </span>
            {expanded ? (
              <ChevronUp className="w-3.5 h-3.5" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* Quick Inline Schedule Controls */}
      <div className="mt-4 pt-3 border-t border-slate-800/80 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-12 gap-3 items-end">
        {/* Search Query to Monitor */}
        <div className="lg:col-span-4">
          <div className="flex items-center justify-between mb-1">
            <label className="text-[11px] font-semibold text-slate-300">
              Ricerca da Monitorare su Vinted
            </label>
            <button
              type="button"
              onClick={handleSyncFromSearchBar}
              className="text-[10px] text-amber-400 hover:underline font-semibold"
            >
              Copia da ricerca sopra
            </button>
          </div>
          <input
            type="text"
            data-testid="radar-query-input"
            value={form.query}
            onChange={(e) => updateField('query', e.target.value)}
            placeholder="es. Orient Star, Seiko 6139, Citizen Promaster..."
            className="w-full px-3 py-2 rounded-xl bg-slate-950/90 border border-slate-700 focus:border-emerald-400 focus:outline-none text-xs text-white"
          />
        </div>

        {/* Max Price EUR */}
        <div className="lg:col-span-2">
          <label className="block text-[11px] font-semibold text-slate-300 mb-1">
            Prezzo Max (€)
          </label>
          <input
            type="number"
            min="10"
            max="10000"
            step="10"
            value={form.max_price || ''}
            onChange={(e) => updateField('max_price', e.target.value)}
            className="w-full px-3 py-2 rounded-xl bg-slate-950/90 border border-slate-700 focus:border-emerald-400 focus:outline-none text-xs text-white font-mono"
          />
        </div>

        {/* Interval in Minutes (Preset Chips + Custom Input) */}
        <div className="lg:col-span-4">
          <label className="block text-[11px] font-semibold text-slate-300 mb-1 flex items-center gap-1">
            <Clock className="w-3 h-3 text-emerald-400" />
            Frequenza Scansione (Ogni quanti minuti)
          </label>
          <div className="flex items-center gap-1.5">
            {INTERVAL_PRESETS.map((mins) => (
              <button
                key={mins}
                type="button"
                onClick={() => updateField('interval_minutes', mins)}
                className={`px-2.5 py-2 rounded-lg text-xs font-bold border transition ${
                  Number(form.interval_minutes) === mins
                    ? 'bg-emerald-500/25 border-emerald-400 text-emerald-200'
                    : 'bg-slate-900 border-slate-700 text-slate-400 hover:text-white'
                }`}
              >
                {mins}m
              </button>
            ))}
            <input
              type="number"
              min="1"
              max="1440"
              data-testid="radar-interval-input"
              value={form.interval_minutes}
              onChange={(e) => updateField('interval_minutes', e.target.value)}
              className="w-16 px-2 py-2 rounded-lg bg-slate-950 border border-slate-700 text-xs text-center text-white font-mono"
              title="Inserisci qualsiasi intervallo in minuti (1 - 1440)"
            />
            <span className="text-[11px] text-slate-400">min</span>
          </div>
        </div>

        {/* Min Deal Score Threshold */}
        <div className="lg:col-span-2">
          <label className="block text-[11px] font-semibold text-slate-300 mb-1">
            Avvisa se Deal Score &gt;=
          </label>
          <select
            value={form.min_deal_score}
            onChange={(e) => updateField('min_deal_score', Number(e.target.value))}
            className="w-full px-2.5 py-2 rounded-xl bg-slate-950/90 border border-slate-700 focus:border-emerald-400 focus:outline-none text-xs text-white font-semibold"
          >
            <option value={6}>Score &gt;= 6 (Buoni + Trattabili)</option>
            <option value={7}>Score &gt;= 7 (Veri Affari • Consigliato)</option>
            <option value={8}>Score &gt;= 8 (Solo Top Deal Alto Margine)</option>
            <option value={9}>Score &gt;= 9 (Solo Gemme Rare / Compra Subito)</option>
          </select>
        </div>
      </div>

      {/* Feedback Banner */}
      {feedback && (
        <div
          className={`mt-3 p-2.5 rounded-xl border text-xs flex items-center justify-between gap-2 ${
            feedback.ok
              ? 'bg-emerald-950/50 border-emerald-500/40 text-emerald-200'
              : 'bg-rose-950/50 border-rose-500/40 text-rose-200'
          }`}
        >
          <div className="flex items-center gap-2">
            {feedback.ok ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            )}
            <span>{feedback.text}</span>
          </div>
          <button
            type="button"
            onClick={() => setFeedback(null)}
            className="text-[10px] text-slate-400 hover:text-white"
          >
            Chiudi
          </button>
        </div>
      )}

      {/* Expandable Section: Telegram + WhatsApp Credentials & Notification History */}
      {expanded && (
        <div className="mt-4 pt-4 border-t border-slate-800 space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Telegram Box */}
            <div className="p-4 rounded-xl bg-slate-950/80 border border-sky-500/30 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Send className="w-4 h-4 text-sky-400" />
                  <h3 className="text-xs font-extrabold text-sky-300 uppercase tracking-wider">
                    Notifiche Telegram (Bot API Ufficiale • Gratis)
                  </h3>
                </div>
                <label className="inline-flex items-center gap-2 cursor-pointer text-xs text-sky-200 font-semibold">
                  <input
                    type="checkbox"
                    checked={Boolean(form.telegram_enabled)}
                    onChange={(e) => updateField('telegram_enabled', e.target.checked)}
                    className="w-4 h-4 rounded accent-sky-500"
                  />
                  <span>Attiva Telegram</span>
                </label>
              </div>

              <p className="text-[11px] text-slate-400">
                Ricevi in tempo reale la foto dell&apos;orologio, il margine stimato e il bottone diretto per aprire l&apos;annuncio su Vinted.
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs">
                <label className="block">
                  <span className="text-[11px] text-slate-300">Telegram Bot Token (@BotFather)</span>
                  <input
                    type="password"
                    placeholder="es. 712345678:AAH..."
                    value={form.telegram_bot_token || ''}
                    onChange={(e) => updateField('telegram_bot_token', e.target.value)}
                    className="mt-1 w-full px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-white font-mono text-xs"
                  />
                </label>
                <label className="block">
                  <span className="text-[11px] text-slate-300">Telegram Chat ID (@userinfobot)</span>
                  <input
                    type="text"
                    placeholder="es. 123456789"
                    value={form.telegram_chat_id || ''}
                    onChange={(e) => updateField('telegram_chat_id', e.target.value)}
                    className="mt-1 w-full px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-white font-mono text-xs"
                  />
                </label>
              </div>
            </div>

            {/* WhatsApp Box */}
            <div className="p-4 rounded-xl bg-slate-950/80 border border-emerald-500/30 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <MessageCircle className="w-4 h-4 text-emerald-400" />
                  <h3 className="text-xs font-extrabold text-emerald-300 uppercase tracking-wider">
                    Notifiche WhatsApp (CallMeBot / Webhook / Link Rapido)
                  </h3>
                </div>
                <label className="inline-flex items-center gap-2 cursor-pointer text-xs text-emerald-200 font-semibold">
                  <input
                    type="checkbox"
                    checked={Boolean(form.whatsapp_enabled)}
                    onChange={(e) => updateField('whatsapp_enabled', e.target.checked)}
                    className="w-4 h-4 rounded accent-emerald-500"
                  />
                  <span>Attiva WhatsApp</span>
                </label>
              </div>

              <p className="text-[11px] text-slate-400">
                Inserisci il tuo numero (+39...) e la API key gratuita CallMeBot (oppure usa il pulsante WhatsApp 1-Click nel registro sotto).
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs">
                <label className="block">
                  <span className="text-[11px] text-slate-300">Numero WhatsApp (con +39)</span>
                  <input
                    type="text"
                    placeholder="es. +393331234567"
                    value={form.whatsapp_phone || ''}
                    onChange={(e) => updateField('whatsapp_phone', e.target.value)}
                    className="mt-1 w-full px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-white font-mono text-xs"
                  />
                </label>
                <label className="block">
                  <span className="text-[11px] text-slate-300">CallMeBot API Key (opzionale)</span>
                  <input
                    type="password"
                    placeholder="es. 123456"
                    value={form.whatsapp_apikey || ''}
                    onChange={(e) => updateField('whatsapp_apikey', e.target.value)}
                    className="mt-1 w-full px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-white font-mono text-xs"
                  />
                </label>
              </div>
            </div>
          </div>

          {/* Save & Test Buttons */}
          <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-900/90 p-3 rounded-xl border border-slate-800">
            <div className="text-[11px] text-slate-400 font-mono">
              Giri eseguiti: <strong className="text-white">{status.total_runs}</strong> •
              Ultimo giro: <strong className="text-slate-200">{status.last_run_at || 'Mai'}</strong> •
              Alert inviati: <strong className="text-emerald-400">{status.total_alerts_sent}</strong>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={handleSendTestAlert}
                data-testid="test-alert-btn"
                className="px-3.5 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 text-white font-bold text-xs flex items-center gap-1.5 shadow transition"
              >
                <Send className="w-3.5 h-3.5" />
                <span>Invia Alert di Prova Ora</span>
              </button>

              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  saveConfigToServer(
                    {
                      ...form,
                      interval_minutes: Math.max(1, Number(form.interval_minutes) || 15),
                      max_price: Number(form.max_price) || 350,
                      min_deal_score: Number(form.min_deal_score) || 7,
                    },
                    'Configurazione Radar e canali di notifica salvati!'
                  )
                }
                className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs shadow transition"
              >
                Salva Impostazioni Notifiche
              </button>
            </div>
          </div>

          {/* Recent Notifications Log */}
          <div className="space-y-2.5">
            <h4 className="text-xs font-extrabold uppercase tracking-wider text-amber-300 flex items-center gap-1.5">
              <Bell className="w-3.5 h-3.5" />
              Ultimi Orologi Interessanti Segnalati dal Radar ({status.recent_notifications?.length || 0})
            </h4>

            {(!status.recent_notifications || status.recent_notifications.length === 0) ? (
              <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 text-xs text-slate-400 text-center">
                Nessuna notifica ancora inviata. Clicca su &quot;Esegui Giro Ora&quot; o &quot;Invia Alert di Prova Ora&quot; per testare subito il link veloce a Vinted!
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-72 overflow-y-auto pr-1">
                {status.recent_notifications.map((entry) => (
                  <div
                    key={entry.id}
                    className="p-3 rounded-xl bg-slate-950/90 border border-slate-800 flex items-center justify-between gap-3"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      {entry.photo_url ? (
                        <img
                          src={entry.photo_url}
                          alt={entry.identified_brand_model}
                          className="w-12 h-12 rounded-lg object-cover border border-slate-700 shrink-0"
                        />
                      ) : (
                        <div className="w-12 h-12 rounded-lg bg-slate-800 flex items-center justify-center text-amber-400 font-bold text-xs shrink-0">
                          {entry.deal_score}/10
                        </div>
                      )}
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-extrabold text-[10px]">
                            Score {entry.deal_score}/10
                          </span>
                          <span className="text-xs font-bold text-white truncate">
                            {entry.identified_brand_model}
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-300 font-mono mt-0.5">
                          Vinted: <strong className="text-amber-300">€{entry.price_listed_eur}</strong> •
                          Valore: €{entry.estimated_market_value_eur_min}-€{entry.estimated_market_value_eur_max} (
                          <span className="text-emerald-400">
                            {entry.net_margin_potential_eur >= 0 ? '+' : ''}€{entry.net_margin_potential_eur}
                          </span>
                          )
                        </div>
                        <div className="text-[10px] text-slate-400 truncate mt-0.5">
                          {entry.delivery_status} • {entry.created_at}
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-col sm:flex-row items-center gap-1.5 shrink-0">
                      {entry.whatsapp_quick_link && (
                        <a
                          href={entry.whatsapp_quick_link}
                          target="_blank"
                          rel="noopener noreferrer"
                          title="Invia o apri questo affare direttamente su WhatsApp"
                          className="px-2.5 py-1.5 rounded-lg bg-emerald-600/25 hover:bg-emerald-600/40 border border-emerald-500/40 text-emerald-200 text-[11px] font-bold flex items-center gap-1 transition"
                        >
                          <MessageCircle className="w-3.5 h-3.5" />
                          <span>WhatsApp</span>
                        </a>
                      )}
                      <a
                        href={entry.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="px-2.5 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 text-[11px] font-extrabold flex items-center gap-1 shadow transition"
                      >
                        <span>Vinted</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
