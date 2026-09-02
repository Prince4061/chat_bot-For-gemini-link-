# ---------- Stage 1: build the React frontend ----------
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: Python runtime ----------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend /app/frontend/dist ./frontend/dist

# SQLite file, agent workspace and logs live on a volume
RUN mkdir -p /data && useradd -r -u 1001 vending && chown -R vending:vending /app /data
USER vending
ENV DATABASE_URL=sqlite:////data/vending_bot.db AGENT_WORKSPACE_DIR=/data/agent_workspace LOG_FILE=/data/logs/app.log

EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fs http://localhost:5000/api/health || exit 1

# One worker (SQLite + in-process caches), many threads. Scale horizontally only with Postgres.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "16", "--timeout", "120", "app:app"]
