#!/usr/bin/env bash
# Evolution API me webhook set karta hai taaki incoming WhatsApp messages
# aapke bot ko forward hon. VPS ke andar se chalao (jahan Evolution + bot dono hain).
#
# Usage:
#   ./setup_evolution_webhook.sh <EVOLUTION_API_KEY> [INSTANCE] [BOT_URL] [WEBHOOK_SECRET] [EVOLUTION_URL]
#
# Example (Case A — same VPS):
#   ./setup_evolution_webhook.sh myEvoKey123 prince http://localhost:5000 mera-secret-123 http://localhost:8080
set -euo pipefail

API_KEY="${1:?Evolution API key chahiye (pehla argument)}"
INSTANCE="${2:-prince}"
BOT_URL="${3:-http://localhost:5000}"
SECRET="${4:-}"
EVOLUTION_URL="${5:-http://localhost:8080}"

WEBHOOK_URL="${BOT_URL%/}/api/webhook/evolution"
if [ -n "$SECRET" ]; then
  WEBHOOK_URL="${WEBHOOK_URL}?token=${SECRET}"
fi

echo "Evolution : $EVOLUTION_URL"
echo "Instance  : $INSTANCE"
echo "Webhook   : $WEBHOOK_URL"
echo

curl -sS -X POST "${EVOLUTION_URL%/}/webhook/set/${INSTANCE}" \
  -H "apikey: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"webhook\":{\"enabled\":true,\"url\":\"${WEBHOOK_URL}\",\"events\":[\"MESSAGES_UPSERT\"]}}"

echo
echo "Done. Ab kisi doosre WhatsApp se apne connected number pe 'products dikhao' bhejo."
echo "Agar 404/format error aaye to Evolution version alag hai — Manager UI (Events/Integrations) se webhook set karo."
