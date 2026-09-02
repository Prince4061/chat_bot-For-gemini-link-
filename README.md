# 🤖 AI Deep Agent — Digital Product Vending & Reseller Management

Production-ready autonomous sales agent built with **Flask + LangGraph + OpenAI**, a **ChatGPT-style React UI**, an **authenticated Admin Dashboard**, and a **WhatsApp (Evolution API) channel**.

It sells digital products (Gemini Advanced, Claude Pro, ChatGPT Plus, Canva Pro, Office 365, …) as **single-use invite links**:

* **Customers** browse live prices (base + admin margin %), pay via UPI, send the UTR, and receive a link instantly.
* **Resellers** verify with phone + 4-digit passcode and claim links against a credit wallet (1 credit = 1 link).
* **Admin** controls products, margins, stock, resellers, orders and settings from the dashboard.

---

## ✨ What makes it production-grade

| Area | Guarantee |
|------|-----------|
| **Atomic link burning** | Conditional `UPDATE … WHERE status='available'` + rowcount check — two concurrent claims can never receive the same link (SQLite *and* Postgres). Covered by a concurrency test. |
| **Transactional credits** | Credits are deducted with `WHERE credits_balance >= n`; if stock runs out mid-claim everything rolls back — credits are never lost. |
| **Session-aware Deep Agent** | Tools know the conversation: a verified reseller stays verified (no repeated passcode prompts), orders are tied to the session, a UTR fulfils *this* conversation's order only, and one UTR can never be reused. |
| **Safe fallback** | No OpenAI key / LLM outage → deterministic Hindi/Hinglish rule engine using the same atomic DB operations. If the LLM fails *after* tools ran, business logic is never re-executed. |
| **Admin auth** | Open by default (no key). Set an optional `ADMIN_API_KEY` to require `X-Admin-Token` on every `/api/admin/*` route. Secrets are always returned masked. |
| **Client isolation** | Each browser only sees its own chat sessions (`X-Client-Id`); WhatsApp sessions are admin-only. |
| **Brute-force protection** | Reseller passcodes lock after N failed attempts; admin can unlock. |
| **Hardened webhook** | Optional shared secret, per-message-id de-duplication, async processing so Evolution always gets a fast 200. |
| **Ops** | Rate limiting, security headers, JSON error handlers, rotating logs, health endpoint, waitress/gunicorn, Dockerfile, light DB migrations, pytest suite. |

---

## 🚀 Quick start

### Prerequisites
* Python 3.10+ · Node.js 18+

### 1. Configure
```bash
cp .env.example .env
```
Everything has a sensible default. Optionally set:
```
OPENAI_API_KEY=sk-...                   # optional – without it the rule engine answers
ADMIN_API_KEY=<long random string>      # optional – leave empty for an open admin dashboard
```

### 2. Install & build
```bash
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
```

### 3. Run
```bash
python app.py
```
Open **http://127.0.0.1:5000** → chat as a customer/reseller, or open **Admin** (no login unless you set `ADMIN_API_KEY`).

On Windows you can simply double-click `start_all.bat`.

**Developer mode (hot reload):** `python app.py` in one terminal, `cd frontend && npm run dev` in another → http://localhost:3000.

### 4. Tests
```bash
python -m pytest tests -q
```

---

## 🏭 Production deployment

1. In `.env` set `APP_ENV=production`, a strong `ADMIN_API_KEY`, a `SECRET_KEY`, explicit `CORS_ORIGINS`, and (recommended) `EVOLUTION_WEBHOOK_SECRET`. Start-up **refuses to run** in production with unsafe values.
2. Run behind a reverse proxy (nginx/Caddy) with HTTPS and set `TRUST_PROXY=true`.
3. Server options:
   * `python app.py` → serves with **waitress** automatically when `APP_ENV=production`.
   * Linux: `gunicorn --workers 1 --threads 16 --timeout 120 app:app`
   * Docker: `docker compose up -d --build` (data persisted in the `vending_data` volume).
4. Database: SQLite (WAL) is fine for one server. For multiple workers/servers set `DATABASE_URL=postgresql+psycopg://…` and `pip install "psycopg[binary]"`. Existing databases are migrated automatically on start.
5. Back up `vending_bot.db` (or your Postgres) — it holds inventory, wallets and the audit trail.

> Keep **one worker process** with SQLite. Rate limits, the agent cache and webhook de-duplication are per process; use Postgres before scaling out.

---

## 📱 WhatsApp via Evolution API

Webhook URL to configure in Evolution Manager (event `MESSAGES_UPSERT`):
```
https://YOUR_DOMAIN/api/webhook/evolution?token=<EVOLUTION_WEBHOOK_SECRET>
```
Set `EVOLUTION_API_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE_NAME` in `.env` or the dashboard. Replies are sent through `/message/sendText/{instance}` (v1 and v2 payloads), long replies are chunked, markdown is converted to WhatsApp formatting. Test without a phone from **Admin → WhatsApp Simulator**.

---

## 🧠 How the Deep Agent works

```
user message ─► run_deep_agent_chat()
                 ├─ per-session lock, history window, session context
                 │    (verified reseller, pending order, platform, time)
                 ├─ LangGraph loop: agent ─► tools ─► agent … (bounded)
                 │    tools: catalog · pricing · verify · credits · claim ·
                 │           order · confirm payment · order status · onboarding
                 └─ persist reply + metadata (engine, tools used, plan)
```

* `agent.md` — the agent's operating rules (edit to change behaviour; reloaded automatically).
* `agent_core.py` — engine, caching, context building, rule-based fallback.
* `agent_tools.py` — session-aware LangChain tools (`agent_context.py` carries the session).
* `deep_agents/` — the graph, `write_todos` planning (persisted in state), backends.
* `database.py` — models + all atomic operations (`process_reseller_claim_for`, `fulfill_order`, …).
* `app.py` — REST API, auth, rate limits, webhook. `config.py` — all environment settings.

---

## 🔐 Default demo data (first run only)

| Reseller | Phone | Code | Credits |
|----------|-------|------|---------|
| Rahul Sharma | 9876543210 | 1234 | 25 |
| Amit Patel | 9123456780 | 8899 | 10 |
| Pooja Verma | 9988776655 | 4321 | 3 |

Products: Gemini Advanced ₹630 · Claude Pro ₹810 · ChatGPT Plus ₹507.50 · Canva Pro ₹200 · Office 365 ₹300 (all 1 credit for resellers). Replace them in **Admin → Products** before going live.

---

## 🔌 API overview

| Route | Auth | Purpose |
|-------|------|---------|
| `POST /api/chat` | client id | Talk to the agent |
| `GET /api/chat/sessions`, `GET /api/chat/history/:id` | client id | Own conversations |
| `POST /api/admin/login` | — | Validate admin key |
| `GET /api/admin/metrics`, `/agent/status`, `POST /agent/test` | admin | Dashboard & LLM diagnostics |
| `/api/admin/products[/…/margin]` | admin | Catalogue & live margin |
| `/api/admin/inventory[/bulk-upload]` | admin | Single-use link stock (duplicates skipped) |
| `/api/admin/resellers[/…/credits|unlock]` | admin | Resellers, wallets, lockouts |
| `/api/admin/orders[/…/approve|cancel]` | admin | Orders & manual fulfilment |
| `/api/admin/settings` | admin | UPI, OpenAI, Evolution settings |
| `POST /api/webhook/evolution` | secret | WhatsApp inbound |
| `GET /api/health` | — | Liveness + engine info |
