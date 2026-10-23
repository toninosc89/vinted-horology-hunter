import React, { useState, useEffect, useMemo } from 'react'
import {
  Watch,
  Search,
  SlidersHorizontal,
  Settings,
  Activity,
  ShieldCheck,
  Filter,
  Cpu,
  Coins,
  Zap,
  ArrowRight,
  RefreshCw,
} from 'lucide-react'
import WatchCard from './components/WatchCard.jsx'
import SettingsModal from './components/SettingsModal.jsx'

const PRESET_QUERIES = [
  'Seiko Vintage',
  'Orient Star',
  'Citizen Promaster',
  'Cronografo Meccanico',
]

export default function App() {
  const [query, setQuery] = useState('Seiko Vintage')
  const [maxPrice, setMaxPrice] = useState(500)
  const [maxItems, setMaxItems] = useState(12)
  const [sortOrder, setSortOrder] = useState('smart_relevance')
  const [onlyVerifiedWorking, setOnlyVerifiedWorking] = useState(false)
  const [bypassCache, setBypassCache] = useState(false)

  const [items, setItems] = useState([])
  const [telemetry, setTelemetry] = useState({
    query: 'Seiko Vintage',
    source_mode: 'live',
    items_extracted: 0,
    discarded_tier0_regex: 0,
    discarded_tier0_condition: 0,
    cache_hits_tier0: 0,
    evaluated_tier1: 0,
    promoted_tier1: 0,
    appraised_tier2: 0,
    escalated_tier3: 0,
    total_tokens_used: 0,
    estimated_tokens_saved: 0,
    total_cost_usd: 0.0,
    total_cost_eur: 0.0,
    duration_seconds: 0.0,
    tier0_rejection_reasons: [],
  })

  const [loading, setLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [escalatingId, setEscalatingId] = useState(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [routerSettings, setRouterSettings] = useState({
    gemini_api_key: '',
    openai_api_key: '',
    anthropic_api_key: '',
    groq_api_key: '',
    deepseek_api_key: '',
    openrouter_api_key: '',
    ollama_base_url: 'http://localhost:11434',
    tier1_provider: 'gemini',
    tier1_model: 'gemini-3.1-flash-lite-preview',
    tier2_provider: 'gemini',
    tier2_model: 'gemini-3-flash-preview',
    tier3_provider: 'gemini',
    tier3_model: 'gemini-3-flash-preview',
    auto_optimize_enabled: true,
  })

  useEffect(() => {
    fetchSettings()
    executeScan('Seiko Vintage', 500, 12, false, 'smart_relevance')
  }, [])

  const fetchSettings = async () => {
    try {
      const resp = await fetch('/api/settings')
      if (resp.ok) {
        const data = await resp.json()
        setRouterSettings(data)
      }
    } catch {
      // ignore initial offline error
    }
  }

  const executeScan = async (
    qOverride = query,
    priceOverride = maxPrice,
    itemsOverride = maxItems,
    forceBypass = bypassCache,
    orderOverride = sortOrder
  ) => {
    setLoading(true)
    setErrorMsg('')
    try {
      const resp = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: qOverride,
          max_price: Number(priceOverride) > 0 ? Number(priceOverride) : null,
          max_items: Number(itemsOverride) || 12,
          sort_order: orderOverride,
          only_verified_working: false,
          bypass_cache: Boolean(forceBypass),
        }),
      })
      if (!resp.ok) {
        throw new Error(`Errore server (${resp.status})`)
      }
      const data = await resp.json()
      setItems(data.items || [])
      if (data.telemetry) {
        setTelemetry(data.telemetry)
      }
    } catch (err) {
      setErrorMsg(err.message || 'Errore durante la scansione su Vinted.it')
    } finally {
      setLoading(false)
    }
  }

  const handleSearchSubmit = (e) => {
    e.preventDefault()
    executeScan(query, maxPrice, maxItems, bypassCache, sortOrder)
  }

  const handlePresetClick = (preset) => {
    setQuery(preset)
    executeScan(preset, maxPrice, maxItems, bypassCache, sortOrder)
  }

  const handleEscalateTier3 = async (watchItem) => {
    setEscalatingId(watchItem.vinted_id)
    try {
      const resp = await fetch(`/api/tier3/${watchItem.vinted_id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ appraisal: watchItem }),
      })
      if (resp.ok) {
        const upgraded = await resp.json()
        setItems((prev) =>
          prev
            .map((it) => (it.vinted_id === upgraded.vinted_id ? upgraded : it))
            .sort((a, b) => b.deal_score - a.deal_score)
        )
        setTelemetry((prev) => ({
          ...prev,
          escalated_tier3: prev.escalated_tier3 + 1,
          total_tokens_used:
            prev.total_tokens_used + Math.max(0, upgraded.tokens_used - watchItem.tokens_used),
          total_cost_usd: Number(
            (
              prev.total_cost_usd +
              Math.max(0, upgraded.cost_usd - watchItem.cost_usd)
            ).toFixed(6)
          ),
        }))
      }
    } finally {
      setEscalatingId(null)
    }
  }

  const handleSaveSettings = async (newSettings) => {
    const resp = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newSettings),
    })
    if (resp.ok) {
      const saved = await resp.json()
      setRouterSettings(saved)
    }
  }

  const handleAutoOptimize = async (currentSettings) => {
    const resp = await fetch('/api/settings/auto-optimize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(currentSettings),
    })
    if (resp.ok) {
      const optimized = await resp.json()
      setRouterSettings(optimized)
      return optimized
    }
    return currentSettings
  }

  const displayedItems = useMemo(() => {
    const filtered = onlyVerifiedWorking
      ? items.filter((item) => item.is_working_verified && item.deal_score >= 6)
      : items
    return [...filtered].sort(
      (a, b) => b.deal_score - a.deal_score || b.net_margin_potential_eur - a.net_margin_potential_eur
    )
  }, [items, onlyVerifiedWorking])

  const totalTier0Discarded =
    (telemetry.discarded_tier0_regex || 0) + (telemetry.discarded_tier0_condition || 0)

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-100 flex flex-col">
      {/* Top Navbar */}
      <header className="sticky top-0 z-30 bg-[#090d16]/90 backdrop-blur-md border-b border-slate-800/80 px-4 sm:px-8 py-4">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-amber-500/30 to-amber-700/10 border border-amber-500/40 flex items-center justify-center shadow-lg">
              <Watch className="w-6 h-6 text-amber-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-extrabold tracking-tight text-white">
                  Vinted Horology Hunter
                </h1>
                <span className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30">
                  4-Tier MAS • Solo Marcianti
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Scouting Orologiero On-Demand su Vinted.it con Filtro Anti-Franken & Multi-Provider LLM Router
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden lg:flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-300">
              <Cpu className="w-3.5 h-3.5 text-amber-400" />
              <span>T1: <strong className="text-sky-300">{routerSettings.tier1_model}</strong></span>
              <span className="text-slate-600">•</span>
              <span>T2: <strong className="text-amber-300">{routerSettings.tier2_model}</strong></span>
              <span className="text-slate-600">•</span>
              <span>T3: <strong className="text-purple-300">{routerSettings.tier3_model}</strong></span>
            </div>

            <button
              type="button"
              onClick={() => setSettingsOpen(true)}
              data-testid="open-settings-btn"
              className="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-100 text-xs font-bold flex items-center gap-2 shadow transition"
            >
              <Settings className="w-4 h-4 text-amber-400" />
              <span>LLM Router & API Settings</span>
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto w-full px-4 sm:px-8 py-6 space-y-6 flex-1">
        {/* 1. Top Search & Filter Bar */}
        <section className="bg-[#111827] border border-slate-800 rounded-2xl p-5 shadow-xl space-y-4">
          <form onSubmit={handleSearchSubmit} className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
            {/* Search Query Input (or direct Vinted URL) */}
            <div className="md:col-span-4">
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Ricerca Orologio o Link Diretto Vinted.it
              </label>
              <div className="relative">
                <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  data-testid="search-query-input"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="es. orient star oppure incolla URL vinted.it/items/..."
                  className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-950 border border-slate-700 focus:border-amber-500 focus:outline-none text-sm text-white"
                />
              </div>
            </div>

            {/* Sort Order */}
            <div className="md:col-span-2">
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Ordinamento Vinted
              </label>
              <select
                value={sortOrder}
                onChange={(e) => setSortOrder(e.target.value)}
                className="w-full px-2.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700 focus:border-amber-500 focus:outline-none text-xs text-white"
              >
                <option value="smart_relevance">Smart (Pertinenza + Nuovi)</option>
                <option value="relevance">Più Pertinenti (Default Vinted)</option>
                <option value="newest_first">Più Recenti ( Ultimi Caricati)</option>
              </select>
            </div>

            {/* Max Price (€) */}
            <div className="md:col-span-2">
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Prezzo Max (€)
              </label>
              <input
                type="number"
                min="10"
                max="10000"
                step="10"
                value={maxPrice}
                onChange={(e) => setMaxPrice(e.target.value)}
                className="w-full px-3 py-2.5 rounded-xl bg-slate-950 border border-slate-700 focus:border-amber-500 focus:outline-none text-sm text-white font-mono"
              />
            </div>

            {/* Max Items */}
            <div className="md:col-span-1">
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Max Item
              </label>
              <input
                type="number"
                min="1"
                max="50"
                value={maxItems}
                onChange={(e) => setMaxItems(e.target.value)}
                className="w-full px-2.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700 focus:border-amber-500 focus:outline-none text-sm text-white font-mono"
              />
            </div>

            {/* Submit Search Button */}
            <div className="md:col-span-3">
              <button
                type="submit"
                disabled={loading}
                data-testid="launch-scan-btn"
                className="w-full py-2.5 px-4 rounded-xl bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-slate-950 font-extrabold text-sm flex items-center justify-center gap-2 shadow-lg transition"
              >
                {loading ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Scansione MAS in corso...</span>
                  </>
                ) : (
                  <>
                    <Zap className="w-4 h-4" />
                    <span>Avvia Scansione Vinted</span>
                  </>
                )}
              </button>
            </div>
          </form>

          {/* Preset Chips & Solo Marcianti Verificati Toggle */}
          <div className="pt-2 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-slate-400 flex items-center gap-1 mr-1">
                <SlidersHorizontal className="w-3.5 h-3.5 text-amber-400" />
                Preset Rapidi:
              </span>
              {PRESET_QUERIES.map((preset) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => handlePresetClick(preset)}
                  className={`px-3 py-1 rounded-full text-xs font-semibold border transition ${
                    query.toLowerCase() === preset.toLowerCase()
                      ? 'bg-amber-500/20 border-amber-500 text-amber-300'
                      : 'bg-slate-900 border-slate-700 text-slate-300 hover:border-slate-500'
                  }`}
                >
                  {preset}
                </button>
              ))}
            </div>

            <div className="flex flex-wrap items-center gap-4">
              <label className="inline-flex items-center gap-2.5 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={onlyVerifiedWorking}
                  onChange={(e) => setOnlyVerifiedWorking(e.target.checked)}
                  className="w-4 h-4 rounded accent-amber-500"
                />
                <span className="text-xs font-semibold text-emerald-300 flex items-center gap-1">
                  <ShieldCheck className="w-4 h-4" />
                  Mostra solo Marcianti Verificati (Score &gt;= 6)
                </span>
              </label>

              <label className="inline-flex items-center gap-2 cursor-pointer select-none text-xs text-slate-400">
                <input
                  type="checkbox"
                  checked={bypassCache}
                  onChange={(e) => setBypassCache(e.target.checked)}
                  className="w-3.5 h-3.5 rounded accent-amber-500"
                />
                <span>Ignora Cache SQLite</span>
              </label>
            </div>
          </div>
        </section>

        {/* 2. Live Pipeline & FinOps Telemetry Bar */}
        <section
          data-testid="telemetry-bar"
          className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-lg"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-amber-400">
              <Activity className="w-4 h-4" />
              <span>Telemetria Live Pipeline 4-Tier MAS & FinOps</span>
            </div>
            <div className="text-xs text-slate-400 font-mono">
              Durata: <strong className="text-slate-200">{telemetry.duration_seconds}s</strong> •
               Sorgente: <strong className="text-amber-300">{telemetry.source_mode === 'live' ? 'Vinted.it Live' : 'Catalogo Vinted Verificato'}</strong>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {/* Step 1: Annunci Estratti */}
            <div className="p-3 rounded-xl bg-[#111827] border border-slate-800 flex items-center justify-between">
              <div>
                <div className="text-[11px] text-slate-400">Annunci Estratti</div>
                <div className="text-lg font-extrabold text-white">{telemetry.items_extracted}</div>
              </div>
              <ArrowRight className="w-4 h-4 text-slate-600 hidden sm:block" />
            </div>

            {/* Step 2: Scartati Tier 0 (Regex/Cache) */}
            <div className="p-3 rounded-xl bg-[#111827] border border-slate-800 flex items-center justify-between">
              <div>
                <div className="text-[11px] text-slate-400">Scartati Tier 0 (Regex/Cache)</div>
                <div className="text-lg font-extrabold text-rose-400">
                  {totalTier0Discarded}{' '}
                  <span className="text-xs font-normal text-emerald-400">
                    ({telemetry.cache_hits_tier0} cache)
                  </span>
                </div>
              </div>
              <ArrowRight className="w-4 h-4 text-slate-600 hidden sm:block" />
            </div>

            {/* Step 3: Promossi Tier 1 (Triage) */}
            <div className="p-3 rounded-xl bg-[#111827] border border-slate-800 flex items-center justify-between">
              <div>
                <div className="text-[11px] text-slate-400">Promossi Tier 1 (Triage)</div>
                <div className="text-lg font-extrabold text-sky-400">{telemetry.promoted_tier1}</div>
              </div>
              <ArrowRight className="w-4 h-4 text-slate-600 hidden sm:block" />
            </div>

            {/* Step 4: Periziati Tier 2/3 */}
            <div className="p-3 rounded-xl bg-[#111827] border border-slate-800">
              <div className="text-[11px] text-slate-400">Periziati Tier 2/3</div>
              <div className="text-lg font-extrabold text-amber-400">
                {telemetry.appraised_tier2}{' '}
                <span className="text-xs font-normal text-purple-300">
                  ({telemetry.escalated_tier3} T3)
                </span>
              </div>
            </div>

            {/* Costo Ricerca ($ / €) */}
            <div className="p-3 rounded-xl bg-[#111827] border border-slate-800">
              <div className="text-[11px] text-slate-400 flex items-center gap-1">
                <Coins className="w-3 h-3 text-amber-400" />
                Costo Totale Ricerca
              </div>
              <div className="text-sm font-extrabold text-emerald-400 font-mono mt-0.5">
                ${Number(telemetry.total_cost_usd || 0).toFixed(4)} / €{Number(telemetry.total_cost_eur || 0).toFixed(4)}
              </div>
            </div>

            {/* Token Risparmiati */}
            <div className="p-3 rounded-xl bg-[#111827] border border-slate-800">
              <div className="text-[11px] text-slate-400">Token Usati / Risparmiati</div>
              <div className="text-sm font-extrabold text-slate-200 font-mono mt-0.5">
                {telemetry.total_tokens_used}{' '}
                <span className="text-emerald-400">(-{telemetry.estimated_tokens_saved} salvati)</span>
              </div>
            </div>
          </div>

          {/* Tier 0 Rejection Log Collapsible Pill */}
          {telemetry.tier0_rejection_reasons && telemetry.tier0_rejection_reasons.length > 0 && (
            <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
              <span className="font-semibold text-rose-400 flex items-center gap-1">
                <Filter className="w-3 h-3" />
                Filtro Deterministico "Solo Marcianti" (Tier 0 - $0.00):
              </span>
              {telemetry.tier0_rejection_reasons.slice(0, 4).map((r) => (
                <span
                  key={r.id}
                  className="px-2 py-0.5 rounded bg-rose-950/40 border border-rose-800/40 text-rose-300 truncate max-w-xs"
                  title={`${r.title} -> ${r.reason}`}
                >
                  #{r.id}: {r.reason.replace('Tier 0 Regex Blacklist: ', '')}
                </span>
              ))}
            </div>
          )}
        </section>

        {errorMsg && (
          <div className="p-4 rounded-xl bg-rose-950/50 border border-rose-700 text-rose-200 text-sm">
            {errorMsg}
          </div>
        )}

        {/* 3. Watch Appraisal Grid */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-slate-200 flex items-center gap-2">
              <span>Perizie Orologiere Validate ({displayedItems.length} risultati)</span>
              <span className="text-xs font-normal text-slate-400">
                • Ordinati per Deal Score decrescente
              </span>
            </h2>
          </div>

          {displayedItems.length === 0 && !loading ? (
            <div className="p-12 rounded-2xl bg-[#111827] border border-slate-800 text-center space-y-2">
              <p className="text-sm font-semibold text-slate-300">
                Nessun orologio conforme trovato con i filtri attuali.
              </p>
              <p className="text-xs text-slate-500">
                Prova ad ampliare il Prezzo Max (€) o disattivare il filtro rigoroso Score &gt;= 6.
              </p>
            </div>
          ) : (
            <div
              data-testid="watch-appraisal-grid"
              className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
            >
              {displayedItems.map((item) => (
                <WatchCard
                  key={item.vinted_id}
                  item={item}
                  onEscalateTier3={handleEscalateTier3}
                  isEscalating={escalatingId === item.vinted_id}
                />
              ))}
            </div>
          )}
        </section>
      </main>

      {/* 4. LLM Router & API Settings Modal */}
      <SettingsModal
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        settings={routerSettings}
        onSaveSettings={handleSaveSettings}
        onAutoOptimize={handleAutoOptimize}
      />
    </div>
  )
}
