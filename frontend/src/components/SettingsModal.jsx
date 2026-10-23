import React, { useState, useEffect } from 'react'
import { X, Sparkles, Save, Key, Cpu, Server, CheckCircle2 } from 'lucide-react'

const PROVIDER_MODELS = {
  gemini: [
    'gemini-2.5-flash-lite',
    'gemini-3.8-flash',
    'gemini-2.5-flash',
    'gemini-2.5-pro',
    'gemini-4-argon',
  ],
  openai: ['gpt-4o-mini', 'gpt-4o'],
  anthropic: ['claude-3-5-sonnet-latest', 'claude-3-7-sonnet-latest'],
  groq: ['llama-3.3-70b-versatile', 'llama-3.2-90b-vision-preview'],
  deepseek: ['deepseek-chat', 'deepseek-reasoner'],
  openrouter: ['google/gemini-2.5-flash', 'anthropic/claude-3.5-sonnet'],
  ollama: ['ollama/llama3.2', 'ollama/llava'],
}

export default function SettingsModal({
  isOpen,
  onClose,
  settings,
  onSaveSettings,
  onAutoOptimize,
}) {
  const [formData, setFormData] = useState(settings)
  const [statusMsg, setStatusMsg] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setFormData(settings)
  }, [settings, isOpen])

  if (!isOpen) return null

  const handleChange = (field, value) => {
    setFormData((prev) => {
      const updated = { ...prev, [field]: value }
      if (field === 'tier1_provider') {
        updated.tier1_model = PROVIDER_MODELS[value]?.[0] || ''
      } else if (field === 'tier2_provider') {
        updated.tier2_model = PROVIDER_MODELS[value]?.[0] || ''
      } else if (field === 'tier3_provider') {
        updated.tier3_model = PROVIDER_MODELS[value]?.[0] || ''
      }
      return updated
    })
  }

  const handleAutoOptimizeClick = async () => {
    setSaving(true)
    try {
      const optimized = await onAutoOptimize(formData)
      setFormData(optimized)
      setStatusMsg('Routing ottimizzato automaticamente per Costo/Performance!')
      setTimeout(() => setStatusMsg(''), 3500)
    } finally {
      setSaving(false)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      await onSaveSettings(formData)
      setStatusMsg('Impostazioni LLM Router salvate con successo!')
      setTimeout(() => {
        setStatusMsg('')
        onClose()
      }, 900)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="llm-router-modal-title"
    >
      <div className="bg-[#111827] border border-slate-700 rounded-2xl max-w-3xl w-full shadow-2xl overflow-hidden my-8">
        {/* Modal Header */}
        <div className="px-6 py-4 bg-slate-900 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Cpu className="w-5 h-5 text-amber-400" />
            <h2 id="llm-router-modal-title" className="text-lg font-bold text-slate-100">
              Configurazione Multi-Provider LLM Router & API Keys
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Chiudi modale"
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-6 max-h-[82vh] overflow-y-auto">
          {/* Auto-Optimize Preset Banner */}
          <div className="p-4 rounded-xl bg-gradient-to-r from-amber-500/15 via-purple-500/10 to-emerald-500/15 border border-amber-500/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div>
              <h3 className="text-sm font-bold text-amber-300 flex items-center gap-1.5">
                <Sparkles className="w-4 h-4" />
                Preset FinOps: Auto-Optimize Cost/Performance
              </h3>
              <p className="text-xs text-slate-300 mt-0.5">
                Assegna automaticamente il modello più economico al Triage Batch (Tier 1), il miglior
                modello Vision al Tier 2 e il modello High-Reasoning all'Arbitro Forense (Tier 3).
              </p>
            </div>
            <button
              type="button"
              onClick={handleAutoOptimizeClick}
              disabled={saving}
              className="shrink-0 px-4 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs flex items-center gap-1.5 shadow-lg transition"
            >
              <Sparkles className="w-4 h-4" />
              Auto-Optimize Cost/Performance
            </button>
          </div>

          {statusMsg && (
            <div className="p-3 rounded-xl bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 text-xs font-medium flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{statusMsg}</span>
            </div>
          )}

          {/* Tier Model Selection */}
          <div className="space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <Server className="w-3.5 h-3.5 text-amber-400" />
              Routing Modelli per Livello Agente (Tier 1 • Tier 2 • Tier 3)
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Tier 1 */}
              <div className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 space-y-2">
                <div className="text-xs font-bold text-sky-300">
                  TIER 1 • Batch Triage Screener
                </div>
                <label className="block text-[11px] text-slate-400">
                  Provider Tier 1
                  <select
                    value={formData.tier1_provider}
                    onChange={(e) => handleChange('tier1_provider', e.target.value)}
                    className="mt-1 w-full rounded-lg bg-slate-950 border border-slate-700 px-2.5 py-1.5 text-xs text-slate-100"
                  >
                    {Object.keys(PROVIDER_MODELS).map((p) => (
                      <option key={p} value={p}>{p.toUpperCase()}</option>
                    ))}
                  </select>
                </label>
                <label className="block text-[11px] text-slate-400">
                  Modello Tier 1
                  <input
                    type="text"
                    value={formData.tier1_model}
                    onChange={(e) => handleChange('tier1_model', e.target.value)}
                    className="mt-1 w-full rounded-lg bg-slate-950 border border-slate-700 px-2.5 py-1.5 text-xs text-slate-100 font-mono"
                  />
                </label>
              </div>

              {/* Tier 2 */}
              <div className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 space-y-2">
                <div className="text-xs font-bold text-amber-300">
                  TIER 2 • Vision Horologist
                </div>
                <label className="block text-[11px] text-slate-400">
                  Provider Tier 2
                  <select
                    value={formData.tier2_provider}
                    onChange={(e) => handleChange('tier2_provider', e.target.value)}
                    className="mt-1 w-full rounded-lg bg-slate-950 border border-slate-700 px-2.5 py-1.5 text-xs text-slate-100"
                  >
                    {Object.keys(PROVIDER_MODELS).map((p) => (
                      <option key={p} value={p}>{p.toUpperCase()}</option>
                    ))}
                  </select>
                </label>
                <label className="block text-[11px] text-slate-400">
                  Modello Tier 2
                  <input
                    type="text"
                    value={formData.tier2_model}
                    onChange={(e) => handleChange('tier2_model', e.target.value)}
                    className="mt-1 w-full rounded-lg bg-slate-950 border border-slate-700 px-2.5 py-1.5 text-xs text-slate-100 font-mono"
                  />
                </label>
              </div>

              {/* Tier 3 */}
              <div className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 space-y-2">
                <div className="text-xs font-bold text-purple-300">
                  TIER 3 • Senior Arbitrator
                </div>
                <label className="block text-[11px] text-slate-400">
                  Provider Tier 3
                  <select
                    value={formData.tier3_provider}
                    onChange={(e) => handleChange('tier3_provider', e.target.value)}
                    className="mt-1 w-full rounded-lg bg-slate-950 border border-slate-700 px-2.5 py-1.5 text-xs text-slate-100"
                  >
                    {Object.keys(PROVIDER_MODELS).map((p) => (
                      <option key={p} value={p}>{p.toUpperCase()}</option>
                    ))}
                  </select>
                </label>
                <label className="block text-[11px] text-slate-400">
                  Modello Tier 3
                  <input
                    type="text"
                    value={formData.tier3_model}
                    onChange={(e) => handleChange('tier3_model', e.target.value)}
                    className="mt-1 w-full rounded-lg bg-slate-950 border border-slate-700 px-2.5 py-1.5 text-xs text-slate-100 font-mono"
                  />
                </label>
              </div>
            </div>
          </div>

          {/* API Keys Configuration */}
          <div className="space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <Key className="w-3.5 h-3.5 text-amber-400" />
              Chiavi API Multi-Provider & Endpoint Locale Ollama
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <label className="block">
                <span className="text-slate-300 font-medium">Google Gemini API Key</span>
                <input
                  type="password"
                  placeholder="AIzaSy..."
                  value={formData.gemini_api_key || ''}
                  onChange={(e) => handleChange('gemini_api_key', e.target.value)}
                  className="mt-1 w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-slate-100 font-mono"
                />
              </label>

              <label className="block">
                <span className="text-slate-300 font-medium">OpenAI API Key</span>
                <input
                  type="password"
                  placeholder="sk-..."
                  value={formData.openai_api_key || ''}
                  onChange={(e) => handleChange('openai_api_key', e.target.value)}
                  className="mt-1 w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-slate-100 font-mono"
                />
              </label>

              <label className="block">
                <span className="text-slate-300 font-medium">Anthropic API Key</span>
                <input
                  type="password"
                  placeholder="sk-ant-..."
                  value={formData.anthropic_api_key || ''}
                  onChange={(e) => handleChange('anthropic_api_key', e.target.value)}
                  className="mt-1 w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-slate-100 font-mono"
                />
              </label>

              <label className="block">
                <span className="text-slate-300 font-medium">Groq API Key</span>
                <input
                  type="password"
                  placeholder="gsk_..."
                  value={formData.groq_api_key || ''}
                  onChange={(e) => handleChange('groq_api_key', e.target.value)}
                  className="mt-1 w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-slate-100 font-mono"
                />
              </label>

              <label className="block">
                <span className="text-slate-300 font-medium">DeepSeek API Key</span>
                <input
                  type="password"
                  placeholder="sk-..."
                  value={formData.deepseek_api_key || ''}
                  onChange={(e) => handleChange('deepseek_api_key', e.target.value)}
                  className="mt-1 w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-slate-100 font-mono"
                />
              </label>

              <label className="block">
                <span className="text-slate-300 font-medium">OpenRouter API Key</span>
                <input
                  type="password"
                  placeholder="sk-or-v1-..."
                  value={formData.openrouter_api_key || ''}
                  onChange={(e) => handleChange('openrouter_api_key', e.target.value)}
                  className="mt-1 w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-slate-100 font-mono"
                />
              </label>

              <label className="block sm:col-span-2">
                <span className="text-slate-300 font-medium">Ollama Base URL (Locale)</span>
                <input
                  type="text"
                  placeholder="http://localhost:11434"
                  value={formData.ollama_base_url || 'http://localhost:11434'}
                  onChange={(e) => handleChange('ollama_base_url', e.target.value)}
                  className="mt-1 w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2 text-slate-100 font-mono"
                />
              </label>
            </div>
          </div>

          {/* Modal Footer */}
          <div className="pt-4 border-t border-slate-800 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition"
            >
              Annulla
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-lg transition"
            >
              <Save className="w-4 h-4" />
              <span>Salva Configurazione Router</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
