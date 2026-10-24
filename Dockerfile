# ============================================================================
# STAGE 1: Build React + TailwindCSS Frontend (Vite)
# ============================================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ============================================================================
# STAGE 2: Production Python 3.12 + FastAPI + curl_cffi + Built Frontend
# ============================================================================
FROM python:3.12-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=Europe/Rome \
    HOROLOGY_DB_PATH=/app/data/horology_hunter.db \
    PORT=8000

WORKDIR /app

# Install system libraries required by curl_cffi (libatomic1, libstdc++6, libnss3) & healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    libatomic1 \
    libnss3 \
    libstdc++6 \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r backend/requirements.txt

# Copy backend application code
COPY backend/ ./backend/

# Copy compiled frontend static assets from Stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Create persistent SQLite volume directory with full permissions
RUN mkdir -p /app/data && chmod 777 /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

# Use --loop asyncio so curl_cffi and background scheduler run cleanly without uvloop conflicts
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "asyncio"]
