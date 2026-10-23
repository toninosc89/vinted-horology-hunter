# Vinted Horology Hunter ⌚

Full-stack web application per lo scouting on-demand di orologi su **Vinted.it**, guidata da un **Sistema Multi-Agente (MAS) a 4 livelli** e da un **Multi-Provider LLM Router** ottimizzato per i costi.

## Caratteristiche Principali
- **Scouting Live su Vinted.it (`backend/vinted_client.py`)**: Impersonazione TLS (`curl_cffi` `chrome120`), handshake automatico dei cookie di sessione, estrazione annunci live Stage 1 e Deep Fetch Stage 2 con foto ad alta risoluzione (`/f800/`) e descrizione completa del venditore.
- **Filtro Rigoroso "Solo Marcianti" (`backend/agents/tier0_guardrail.py`)**: Guardrail deterministico regex case-insensitive a costo `$0.00` (scarta orologi rotti, per ricambi o con batteria scarica preservando complicazioni come *"fermo macchina"*) + cache locale SQLite.
- **4-Tier Multi-Agent System (`backend/agents/`)**:
  - **Tier 0**: Regex Blacklist, Condition Filter e Cache SQLite (`0` token).
  - **Tier 1**: Batch Triage Screener (valuta fino a 20 annunci in un singolo prompt).
  - **Tier 2**: Multimodal Horologist & Market Appraiser (verifica visiva quadrante/fondello, controllo Anti-Franken / *Mumbai Special*, stima calibro e calcolo margine netto reale incluso costo protezione acquisti e spedizione Vinted).
  - **Tier 3**: Senior Horology Arbitrator (escalation automatica o manuale on-demand per audit forense e generazione messaggio di trattativa in italiano per il venditore).
- **Multi-Provider LLM Router (`backend/agents/llm_router.py`)**: Supporta Google Gemini, OpenAI, Anthropic, Groq, DeepSeek, OpenRouter e Ollama locale con preset **Auto-Optimize Cost/Performance**.

## Avvio Rapido

### 1. Backend (FastAPI)
```bash
pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Frontend (React + Vite + TailwindCSS)
```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

### 3. Test di Verifica Pipeline
```bash
python -m pytest backend/test_pipeline.py -v
```
