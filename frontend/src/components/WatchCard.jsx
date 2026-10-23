import React, { useState } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  ExternalLink,
  Sparkles,
  Wrench,
  Cpu,
  Coins,
} from 'lucide-react'

export default function WatchCard({ item, onEscalateTier3, isEscalating }) {
  const [photoIdx, setPhotoIdx] = useState(0)
  const [techOpen, setTechOpen] = useState(true)
  const [copied, setCopied] = useState(false)

  const photos = item.photo_urls && item.photo_urls.length > 0
    ? item.photo_urls
    : ['https://placehold.co/400x400/111827/d4af37?text=Orologio+Vinted']

  const prevPhoto = (e) => {
    e.stopPropagation()
    setPhotoIdx((prev) => (prev === 0 ? photos.length - 1 : prev - 1))
  }

  const nextPhoto = (e) => {
    e.stopPropagation()
    setPhotoIdx((prev) => (prev === photos.length - 1 ? 0 : prev + 1))
  }

  const handleCopyMessage = async () => {
    const offerSuffix = item.suggested_offer_eur
      ? ` (Offerta consigliata: €${item.suggested_offer_eur.toFixed(2)})`
      : ''
    const textToCopy = item.suggested_message_to_seller || `Ciao! Sono interessato all'orologio${offerSuffix}.`
    try {
      await navigator.clipboard.writeText(textToCopy)
    } catch {
      // Fallback copy
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 2200)
  }

  // Deal score badge styling (1-10)
  const scoreBadgeClass =
    item.deal_score >= 8
      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
      : item.deal_score >= 6
      ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
      : 'bg-rose-500/20 text-rose-300 border-rose-500/40'

  // Franken / Fake Risk Badge (Verde / Giallo / Rosso)
  const frankenConfig = {
    LOW: {
      label: 'Rischio Franken: BASSO (Verde)',
      classes: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
      Icon: ShieldCheck,
    },
    MEDIUM: {
      label: 'Rischio Franken: MEDIO (Giallo)',
      classes: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
      Icon: AlertTriangle,
    },
    HIGH: {
      label: 'Rischio Franken: ALTO (Rosso)',
      classes: 'bg-rose-500/15 text-rose-300 border-rose-500/40',
      Icon: ShieldAlert,
    },
  }[item.franken_fake_risk] || {
    label: `Rischio: ${item.franken_fake_risk}`,
    classes: 'bg-slate-700 text-slate-200 border-slate-600',
    Icon: AlertTriangle,
  }

  const actionConfig = {
    COMPRA_SUBITO: {
      label: 'COMPRA SUBITO',
      classes: 'bg-emerald-600 text-white border-emerald-400',
    },
    TRATTA_PREZZO: {
      label: 'TRATTA PREZZO',
      classes: 'bg-amber-600 text-white border-amber-400',
    },
    CHIEDI_FOTO_FONDELLO: {
      label: 'CHIEDI FOTO FONDELLO',
      classes: 'bg-sky-600 text-white border-sky-400',
    },
    SCARTA: {
      label: 'SCARTA',
      classes: 'bg-rose-700 text-white border-rose-500',
    },
  }[item.recommended_action] || {
    label: item.recommended_action,
    classes: 'bg-slate-700 text-white border-slate-500',
  }

  const FrankenIcon = frankenConfig.Icon
  const isTier3 = item.tier_reached && item.tier_reached.includes('Tier 3')

  return (
    <article
      data-testid={`watch-card-${item.vinted_id}`}
      className="bg-[#111827] border border-slate-800 hover:border-amber-500/50 rounded-2xl overflow-hidden shadow-xl flex flex-col transition-all duration-200"
    >
      {/* Interactive Image Carousel */}
      <div className="relative h-64 bg-[#0b0f19] flex items-center justify-center overflow-hidden group">
        <img
          src={photos[photoIdx]}
          alt={`${item.identified_brand_model} - foto ${photoIdx + 1}`}
          className="w-full h-full object-contain p-2 transition-transform duration-300 group-hover:scale-105"
        />

        {/* Top Badges Overlay */}
        <div className="absolute top-3 left-3 right-3 flex items-center justify-between gap-2 pointer-events-none">
          <span
            className={`px-3 py-1 rounded-full text-xs font-bold border backdrop-blur-md shadow ${scoreBadgeClass}`}
          >
            Deal Score: {item.deal_score}/10
          </span>
          <span
            className={`px-2.5 py-1 rounded-md text-[11px] font-bold tracking-wide border shadow ${actionConfig.classes}`}
          >
            {actionConfig.label}
          </span>
        </div>

        {/* Photo Counter & Label (Front Dial vs Caseback) */}
        <div className="absolute bottom-2.5 left-3 px-2.5 py-0.5 rounded bg-slate-950/80 border border-slate-800 text-[11px] text-slate-300">
          {photoIdx === 0 ? 'Quadrante Frontale' : `Fondello / Dettaglio (${photoIdx + 1}/${photos.length})`}
        </div>

        {photos.length > 1 && (
          <>
            <button
              type="button"
              onClick={prevPhoto}
              aria-label="Foto precedente"
              className="absolute left-2 top-1/2 -translate-y-1/2 p-1.5 rounded-full bg-slate-900/80 hover:bg-amber-500 hover:text-slate-950 text-slate-200 border border-slate-700 transition"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={nextPhoto}
              aria-label="Foto successiva"
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-full bg-slate-900/80 hover:bg-amber-500 hover:text-slate-950 text-slate-200 border border-slate-700 transition"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </>
        )}
      </div>

      {/* Card Body */}
      <div className="p-5 flex-1 flex flex-col gap-4">
        {/* Title & Identified Model */}
        <div>
          <div className="flex items-center justify-between gap-2 text-xs text-amber-400/90 font-mono mb-1">
            <span>ID #{item.vinted_id}</span>
            <span>Confidenza AI: {Math.round(item.confidence_score * 100)}%</span>
          </div>
          <h3 className="text-base font-bold text-slate-100 leading-snug line-clamp-2">
            {item.identified_brand_model}
          </h3>
          <p className="text-xs text-slate-400 mt-0.5 line-clamp-1" title={item.title}>
            Annuncio: {item.title}
          </p>
        </div>

        {/* Risk & Solo Marcianti & Reference Comparison Badges */}
        <div className="flex flex-wrap items-center gap-2">
          {item.is_best_price_for_ref && item.ref_listings_count > 1 && (
            <span
              data-testid="best-price-ref-badge"
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-extrabold bg-gradient-to-r from-amber-500/25 to-emerald-500/20 text-amber-300 border border-amber-400/50 shadow-sm"
            >
              🏆 Miglior Prezzo per Referenza (su {item.ref_listings_count} annunci)
            </span>
          )}

          {!item.is_best_price_for_ref &&
            item.ref_listings_count > 1 &&
            item.ref_lowest_price_eur != null &&
            item.ref_lowest_price_eur < item.price_listed_eur && (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-amber-950/60 text-amber-300 border border-amber-700/50">
                ⚠️ Stessa Ref. trovata a €{Number(item.ref_lowest_price_eur).toFixed(0)}
              </span>
            )}

          {item.is_duplicate_repost && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-purple-950/60 text-purple-300 border border-purple-700/50">
              🔁 Ripostaggio Duplicato
            </span>
          )}

          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border ${frankenConfig.classes}`}
          >
            <FrankenIcon className="w-3.5 h-3.5" />
            {frankenConfig.label}
          </span>

          <span
            className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium border ${
              item.is_working_verified
                ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                : 'bg-rose-500/15 text-rose-300 border-rose-500/40'
            }`}
          >
            {item.is_working_verified ? '✓ Marciante Verificato' : '✕ Rischio Non Marciante'}
          </span>
        </div>

        {/* Price Breakdown Box */}
        <div className="grid grid-cols-3 gap-2 bg-slate-900/90 border border-slate-800/90 rounded-xl p-3 text-center">
          <div>
            <div className="text-[11px] text-slate-400">Prezzo Vinted</div>
            <div className="text-sm font-bold text-slate-100">
              €{item.price_listed_eur.toFixed(2)}
            </div>
          </div>
          <div className="border-x border-slate-800 px-1">
            <div className="text-[11px] text-slate-400">Costo Totale Finito</div>
            <div className="text-sm font-bold text-amber-300">
              €{item.total_vinted_cost_eur.toFixed(2)}
            </div>
          </div>
          <div>
            <div className="text-[11px] text-slate-400">Valore Mercato</div>
            <div className="text-sm font-bold text-emerald-400">
              €{item.estimated_market_value_eur_min.toFixed(0)}-€{item.estimated_market_value_eur_max.toFixed(0)}
            </div>
          </div>
        </div>

        {/* Net Margin Potential & Deterministic ROI Bar */}
        <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-900/50 border border-slate-800 text-xs">
          <span className="text-slate-400 flex items-center gap-1.5">
            <Coins className="w-3.5 h-3.5 text-amber-400" />
            Margine Netto &amp; ROI:
          </span>
          <div className="flex items-center gap-2">
            <span
              className={`font-bold ${
                item.net_margin_potential_eur >= 0 ? 'text-emerald-400' : 'text-rose-400'
              }`}
            >
              {item.net_margin_potential_eur >= 0 ? '+' : ''}
              €{item.net_margin_potential_eur.toFixed(2)}
            </span>
            {item.roi_pct != null && (
              <span
                className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold border ${
                  item.roi_pct >= 15
                    ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                    : item.roi_pct >= 0
                    ? 'bg-sky-500/15 text-sky-300 border-sky-500/30'
                    : 'bg-rose-500/15 text-rose-300 border-rose-500/30'
                }`}
              >
                {item.roi_pct >= 0 ? '+' : ''}
                {Number(item.roi_pct).toFixed(1)}% ROI
              </span>
            )}
          </div>
        </div>

        {/* Technical Collapsible Section */}
        <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-950/50">
          <button
            type="button"
            onClick={() => setTechOpen(!techOpen)}
            className="w-full px-3.5 py-2.5 flex items-center justify-between text-xs font-semibold text-slate-200 hover:bg-slate-900/80 transition"
          >
            <span className="flex items-center gap-1.5">
              <Wrench className="w-3.5 h-3.5 text-amber-400" />
              Dettagli Tecnici, Calibro & Messaggio Venditore
            </span>
            {techOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>

          {techOpen && (
            <div className="p-3.5 border-t border-slate-800/80 space-y-2.5 text-xs text-slate-300">
              <div>
                <span className="font-semibold text-amber-300">Calibro / Referenza Stimata: </span>
                <span>{item.estimated_reference_caliber}</span>
              </div>
              <div>
                <span className="font-semibold text-emerald-300">Stato di Marcia: </span>
                <span>{item.working_status_notes}</span>
              </div>
              <div>
                <span className="font-semibold text-sky-300">Perizia Autenticità (Anti-Franken): </span>
                <span>{item.authenticity_notes}</span>
              </div>

              {item.suggested_message_to_seller && (
                <div className="pt-2 border-t border-slate-800/80 space-y-2">
                  <div className="flex items-center justify-between text-[11px] text-slate-400">
                    <span>Messaggio Consigliato per il Venditore:</span>
                    {item.suggested_offer_eur && (
                      <span className="text-amber-300 font-semibold">
                        Offerta Consigliata: €{item.suggested_offer_eur.toFixed(2)}
                      </span>
                    )}
                  </div>
                  <p className="p-2.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-200 italic leading-relaxed">
                    "{item.suggested_message_to_seller}"
                  </p>
                  <button
                    type="button"
                    onClick={handleCopyMessage}
                    className="w-full py-2 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-100 font-medium flex items-center justify-center gap-1.5 border border-slate-700 transition"
                  >
                    {copied ? (
                      <>
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="text-emerald-300">Messaggio Copiato negli Appunti!</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5 text-amber-400" />
                        <span>Copia Messaggio per il Venditore</span>
                      </>
                    )}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer Actions: Tier 3 Escalation & Vinted Link */}
        <div className="mt-auto pt-2 flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={isEscalating}
              onClick={() => onEscalateTier3(item)}
              className={`flex-1 py-2.5 px-3 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 border transition ${
                isTier3
                  ? 'bg-purple-950/50 border-purple-500/50 text-purple-200 hover:bg-purple-900/50'
                  : 'bg-gradient-to-r from-amber-500/20 to-purple-500/20 hover:from-amber-500/30 hover:to-purple-500/30 border-amber-500/40 text-amber-200'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5 text-amber-400" />
              {isEscalating
                ? 'Perizia Forense Tier 3 in corso...'
                : isTier3
                ? 'Riesegui Perizia Forense Tier 3'
                : 'Esegui Perizia Forense Tier 3'}
            </button>

            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="py-2.5 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-1 transition"
              title="Apri annuncio su Vinted.it"
            >
              <span>Vinted</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>

          {/* Telemetry Footer */}
          <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1 px-1">
            <span className="flex items-center gap-1 truncate">
              <Cpu className="w-3 h-3 text-slate-400" />
              {item.tier_reached} • {item.model_used}
            </span>
            <span className="font-mono">
              {item.tokens_used} tok (${item.cost_usd.toFixed(4)})
            </span>
          </div>
        </div>
      </div>
    </article>
  )
}
