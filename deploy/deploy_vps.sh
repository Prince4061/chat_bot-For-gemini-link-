#!/usr/bin/env bash
# One-shot (re)deploy on the VPS. Safe to run again and again.
#   ssh root@<vps-ip>
#   cd /root/vending-bot && git pull && bash deploy/deploy_vps.sh
#
# What it does: git pull -> pip deps -> Chromium for the Google link checker (first time only)
#               -> frontend build -> systemctl restart -> health + checker status.
set -euo pipefail

APP_DIR="${APP_DIR:-/root/vending-bot}"
REPO_URL="${REPO_URL:-https://github.com/Prince4061/chat_bot-For-gemini-link-.git}"
SERVICE="${SERVICE:-vending-bot}"
PORT="${PORT:-5000}"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m✔ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo -i)"; exit 1; }

# ---------- 0. code ----------
if [ ! -d "$APP_DIR/.git" ]; then
  say "Cloning $REPO_URL -> $APP_DIR"
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"
say "Pulling latest code"
git pull --ff-only
ok "at commit $(git rev-parse --short HEAD): $(git log -1 --pretty=%s)"

# ---------- 1. system packages ----------
say "System packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-pip git curl >/dev/null
if ! command -v node >/dev/null 2>&1; then
  warn "Node.js missing -> installing Node 20"
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null
  apt-get install -y -qq nodejs >/dev/null
fi
ok "python $(python3 --version 2>&1 | awk '{print $2}'), node $(node --version)"

# ---------- 2. python deps ----------
say "Python dependencies"
# Ubuntu 23.04+ blocks system-wide pip unless --break-system-packages is given (no venv on this box).
pip3 install -q -r requirements.txt 2>/dev/null || pip3 install -q --break-system-packages -r requirements.txt
ok "requirements installed"

# ---------- 3. Chromium for the Google link checker ----------
say "Chromium for google_checker (first run downloads ~300 MB)"
if python3 - <<'PY'
import sys
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox"]); b.close()
except Exception as e:
    print("chromium not ready:", e); sys.exit(1)
PY
then ok "Chromium already installed"
else
  python3 -m playwright install --with-deps chromium
  ok "Chromium installed"
fi

# ---------- 4. frontend ----------
say "Frontend build"
( cd frontend && npm install --no-audit --no-fund --silent && npm run build --silent )
ok "frontend/dist built"

# ---------- 5. service ----------
say "Restarting $SERVICE"
if [ ! -f "/etc/systemd/system/$SERVICE.service" ]; then
  cp deploy/vending-bot.service "/etc/systemd/system/$SERVICE.service"
  systemctl daemon-reload
  systemctl enable "$SERVICE" >/dev/null
fi
[ -f .env ] || warn ".env missing! copy the template from deploy/DEPLOY_VPS.md section 4"
systemctl restart "$SERVICE"

# ---------- 6. health ----------
say "Health check"
for i in $(seq 1 20); do
  if curl -fs "http://127.0.0.1:$PORT/api/health" >/tmp/health.json 2>/dev/null; then break; fi
  sleep 1
done
if [ -s /tmp/health.json ]; then
  ok "bot is up: $(cat /tmp/health.json)"
else
  warn "bot did not answer on :$PORT — last log lines:"
  journalctl -u "$SERVICE" -n 40 --no-pager
  exit 1
fi

ADMIN_KEY="$(grep -E '^ADMIN_API_KEY=' .env 2>/dev/null | cut -d= -f2- | tr -d '"' || true)"
CHK="$(curl -fs -H "X-Admin-Token: ${ADMIN_KEY}" "http://127.0.0.1:$PORT/api/admin/google-checker/status" || true)"
if [ -n "$CHK" ]; then ok "google checker: $CHK"; else warn "could not read checker status (admin key?)"; fi

say "Done. Bot: http://$(hostname -I | awk '{print $1}'):$PORT   Logs: journalctl -u $SERVICE -f"
