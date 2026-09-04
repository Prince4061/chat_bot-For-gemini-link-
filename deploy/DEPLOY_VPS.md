# 🚀 Bot ko VPS pe live karo + WhatsApp (Evolution API) se connect (Case A)

**Case A = Evolution API aur aapka bot dono ek hi VPS pe.** Ye sabse aasan hai — dono
`localhost` se baat karte hain, koi domain/ngrok nahi chahiye.

Aapke values (screenshot se):
- VPS IP: `187.127.132.18`
- Evolution: `http://localhost:8080` (VPS ke andar se)
- Instance name: **`prince`**  ← bot me yahi daalna hai

---

## 0. SSH se VPS me ghuso
```bash
ssh root@187.127.132.18
```

## 1. Zaroori software install karo (Ubuntu/Debian)
```bash
apt update
apt install -y python3 python3-pip python3-venv git curl
# Node.js 20 (frontend build ke liye)
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs
```

## 2. Project code VPS pe laao
**Option A — GitHub se (agar aapne push kiya hai):**
```bash
cd /root
git clone <aapki-repo-url> vending-bot
cd vending-bot
```
**Option B — apne PC se upload (agar GitHub pe nahi hai):** apne PC pe (PowerShell):
```bash
scp -r "G:\Chat_BOT\Chat BOt" root@187.127.132.18:/root/vending-bot
```
Phir VPS pe: `cd /root/vending-bot`

## 3. Python + frontend dependencies
```bash
cd /root/vending-bot
pip3 install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
```

## 4. `.env` banao
```bash
nano .env
```
Ye paste karo (apne asli values daalo):
```
APP_ENV=production
HOST=0.0.0.0
PORT=5000

# Admin ab public hai -> zaroor set karo (koi lamba random string)
ADMIN_API_KEY=badal-ke-koi-lamba-random-string
SECRET_KEY=badal-ke-koi-random-hex
CORS_ORIGINS=http://187.127.132.18:5000

# OpenAI (na do to rule-engine chalega)
OPENAI_API_KEY=sk-...
OPENAI_MODEL_NAME=gpt-4o-mini

# Evolution API (same VPS)
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=<Evolution ka AUTHENTICATION_API_KEY>
EVOLUTION_INSTANCE_NAME=prince
EVOLUTION_WEBHOOK_SECRET=mera-secret-123
```
Save: `Ctrl+O`, Enter, `Ctrl+X`.

> `SECRET_KEY` banane ke liye: `python3 -c "import secrets;print(secrets.token_hex(32))"`
> `ADMIN_API_KEY` ke liye: `python3 -c "import secrets;print(secrets.token_urlsafe(24))"`

## 5. Bot ko service bana ke chalao (auto-restart + reboot pe on)
```bash
cp deploy/vending-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now vending-bot
systemctl status vending-bot        # 'active (running)' dikhna chahiye
```
Bot ab chal raha hai: `http://187.127.132.18:5000`
Logs: `journalctl -u vending-bot -f`

## 6. Firewall me ports kholo
```bash
ufw allow 5000/tcp
ufw allow 8080/tcp
```
(Agar Hostinger panel me firewall hai to wahan bhi 5000 & 8080 allow karo.)

## 7. WhatsApp number connect karo (QR)
Evolution Manager kholo → instance **prince** → **Get QR Code** →
phone me **WhatsApp → Linked Devices → Link a Device** → scan.
Status **green / "open"** ho jaana chahiye.

## 8. Webhook set karo (bot ki taraf)
VPS pe project folder me:
```bash
chmod +x deploy/setup_evolution_webhook.sh
./deploy/setup_evolution_webhook.sh <EVOLUTION_API_KEY> prince http://localhost:5000 mera-secret-123 http://localhost:8080
```
Ya Manager UI → **Events / Integrations → Webhook**:
- Enabled: ON
- URL: `http://localhost:5000/api/webhook/evolution?token=mera-secret-123`
- Event: sirf `MESSAGES_UPSERT`

## 9. Test 🎉
Kisi **doosre** WhatsApp se apne connected number pe bhejo: **"products dikhao"**
→ bot khud reply karega. Bina phone ke test: bot ka **Admin → WhatsApp Simulator**.

---

## Health check
```bash
curl http://localhost:5000/api/health
# {"status":"online", "engine":"deep_agent"/"rule_based_fallback", ...}
```

## Aksar aane wali dikkatein
| Problem | Fix |
|---|---|
| Reply nahi aaya | `journalctl -u vending-bot -f` dekho — webhook hit ho rahi? |
| webhook set pe 404 | Evolution version alag — Manager UI se webhook set karo |
| bot Evolution ko nahi bhej pa raha | `.env` me `EVOLUTION_API_URL=http://localhost:8080`, key/instance sahi? |
| `localhost:5000` webhook fail | `http://127.0.0.1:5000/...` try karo |
| admin koi bhi khol le raha | `.env` me `ADMIN_API_KEY` set karke `systemctl restart vending-bot` |
| number baar-baar disconnect | phone online rakho; instance restart + dobara QR |

## Update deploy karna (baad me code badla to)
```bash
cd /root/vending-bot
git pull                 # ya naya code upload
pip3 install -r requirements.txt
cd frontend && npm run build && cd ..
systemctl restart vending-bot
```

> ⚠️ Ye automated WhatsApp messaging hai. WhatsApp ke terms ka dhyaan rakho —
> known customers/chhote scale ke liye theek; bade scale pe official WhatsApp Cloud API behtar.
