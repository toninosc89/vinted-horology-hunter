# Vinted Horology Hunter ⌚

Full-stack web application per lo scouting on-demand e periodico di orologi su **Vinted.it**, guidata da un **Sistema Multi-Agente (MAS) a 4 livelli**, un **Multi-Provider LLM Router FinOps-Optimized** e un **Radar Automatico con Alert Telegram / WhatsApp**.

## Caratteristiche Principali
- **Scouting Live su Vinted.it (`backend/vinted_client.py`)**: Impersonazione TLS (`curl_cffi` `chrome120`), handshake automatico dei cookie di sessione, estrazione annunci live Stage 1, Deep Fetch Stage 2 con foto ad alta risoluzione (`/f800/`) e **Analizzatore Istantaneo Singolo Link Vinted**.
- **Filtro Rigoroso "Solo Marcianti" (`backend/agents/tier0_guardrail.py`)**: Guardrail deterministico regex case-insensitive a costo `€0.00` (scarta orologi rotti, per ricambi, con batteria scarica o non-orologi come scatole/cinturini) + Cache locale SQLite.
- **4-Tier Multi-Agent System & FinOps Ultra-Efficiency (`backend/agents/`)**:
  - **Tier 0**: Regex Blacklist, Condition Filter, Deduplicazione Ripostaggi e Cache SQLite (`0` token).
  - **Tier 1**: Batch Triage Screener (valuta fino a 20 annunci in un singolo prompt e promuove i Top 8).
  - **Tier 2**: Multimodal Horologist & Market Appraiser (`gemini-3.1-flash-lite-preview` con `thinkingBudget: 0` e quotazione canonica unificata per referenza in SQLite).
  - **Tier 3**: Senior Horology Arbitrator On-Demand (audit forense + verifica prezzi di mercato web tramite scraper Python gratuito `€0.00` + messaggio di trattativa in italiano).
- **Radar Scansione Periodica On-Demand & Notifiche (`backend/notifier.py`)**: Schedulatore integrato attivabile dalla UI ogni `N` minuti con invio istantaneo di foto, margine netto e link veloce a Vinted su **Telegram** e **WhatsApp**.

---

## 🐳 Deploy con Docker sul Tuo Server (Consigliato)

L'applicazione include un [`Dockerfile`](Dockerfile) multi-stage (Node 20 Alpine + Python 3.11 Slim) che compila il frontend React e lo serve direttamente da FastAPI sulla porta `8000` in un **unico container leggero**, salvando database SQLite, cache perizie, chiavi API e impostazioni del Radar nel volume persistente `./data`.

```bash
# 1. Clona il repository sul tuo server Linux / VPS
git clone https://github.com/toninosc89/vinted-horology-hunter.git
cd vinted-horology-hunter

# 2. (Opzionale) Crea il file .env partendo dal template
cp .env.example .env

# 3. Avvia il container in background con riavvio automatico
docker compose up -d --build
```

Una volta avviato, apri nel browser **`http://IP-DEL-TUO-SERVER:8000`**!

### Aggiornare l'app sul server quando escono modifiche su GitHub
```bash
git pull origin main
docker compose up -d --build
```

---

## 💻 Sviluppo Locale (Senza Docker)

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
