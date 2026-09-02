"""
Evolution API (WhatsApp) integration: inbound payload parsing + outbound replies.

Compatible with Evolution API v1 (`textMessage.text`) and v2 (`text`) send formats.
"""
import time
import logging
from typing import Dict, Any, Optional, List

import requests

from config import Config
from database import get_db, get_settings, normalize_phone

logger = logging.getLogger(__name__)

WHATSAPP_MAX_CHARS = 3900  # WhatsApp hard limit is 4096; leave headroom.


def _extract_text(message_obj: Dict[str, Any]) -> str:
    if not isinstance(message_obj, dict):
        return ""
    if message_obj.get("conversation"):
        return str(message_obj["conversation"])
    ext = message_obj.get("extendedTextMessage") or {}
    if ext.get("text"):
        return str(ext["text"])
    btn = message_obj.get("buttonsResponseMessage") or {}
    if btn.get("selectedButtonId") or btn.get("selectedDisplayText"):
        return str(btn.get("selectedDisplayText") or btn.get("selectedButtonId"))
    lst = message_obj.get("listResponseMessage") or {}
    reply = lst.get("singleSelectReply") or {}
    if reply.get("selectedRowId") or lst.get("title"):
        return str(lst.get("title") or reply.get("selectedRowId"))
    tmpl = message_obj.get("templateButtonReplyMessage") or {}
    if tmpl.get("selectedDisplayText"):
        return str(tmpl["selectedDisplayText"])
    for media_key in ("imageMessage", "videoMessage", "documentMessage"):
        media = message_obj.get(media_key) or {}
        if media.get("caption"):
            return str(media["caption"])
    # Ephemeral / view-once wrappers
    for wrapper in ("ephemeralMessage", "viewOnceMessage", "viewOnceMessageV2"):
        inner = (message_obj.get(wrapper) or {}).get("message")
        if inner:
            return _extract_text(inner)
    return ""


def parse_evolution_webhook_payload(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Normalise an Evolution API webhook payload (v1/v2, single or batched `data`).
    Returns None for anything that is not an inbound private text message.
    """
    try:
        event = str(payload.get("event") or "").lower().replace("_", ".")
        if event and "messages.upsert" not in event and "message" not in event:
            return None

        data = payload.get("data", {})
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            return None

        key = data.get("key", {}) or {}
        if key.get("fromMe", False):
            return None
        remote_jid = str(key.get("remoteJid") or "")
        if not remote_jid or "@g.us" in remote_jid or "status@broadcast" in remote_jid:
            return None

        text = _extract_text(data.get("message", {}) or {}).strip()
        if not text:
            return None

        phone_raw = remote_jid.split("@")[0].split(":")[0]
        return {
            "phone": normalize_phone(phone_raw),
            "remote_jid": remote_jid,
            "sender_name": (data.get("pushName") or "WhatsApp User")[:100],
            "text": text[: Config.MAX_MESSAGE_LENGTH],
            "message_id": key.get("id"),
            "instance": payload.get("instance"),
        }
    except Exception:  # noqa: BLE001
        logger.exception("Error parsing Evolution webhook payload")
        return None


def _chunk_text(text: str, limit: int = WHATSAPP_MAX_CHARS) -> List[str]:
    if len(text) <= limit:
        return [text]
    chunks, current = [], ""
    for para in text.split("\n"):
        if len(current) + len(para) + 1 > limit:
            chunks.append(current.rstrip())
            current = ""
        current += para + "\n"
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


def _markdown_to_whatsapp(text: str) -> str:
    """WhatsApp uses *bold* / _italic_ / ```code```; strip markdown it doesn't understand."""
    out = text.replace("**", "*")
    out = out.replace("### ", "").replace("## ", "").replace("# ", "")
    out = out.replace("`", "")
    return out


def send_whatsapp_message(remote_jid: str, message_text: str, custom_instance: Optional[str] = None) -> Dict[str, Any]:
    """POST /message/sendText/{instance}, with chunking for long replies and simple retries."""
    db = get_db()
    try:
        settings = get_settings(db)
        base_url = (settings.evolution_api_url or Config.EVOLUTION_API_URL).rstrip("/")
        api_key = settings.evolution_api_key or Config.EVOLUTION_API_KEY
        instance = custom_instance or settings.evolution_instance_name or Config.EVOLUTION_INSTANCE_NAME
    finally:
        db.close()

    if not base_url or not api_key:
        logger.warning("Evolution API URL/key not configured; skipping WhatsApp send.")
        return {"success": False, "error": "Evolution API not configured"}

    endpoint = f"{base_url}/message/sendText/{instance}"
    headers = {"Content-Type": "application/json", "apikey": api_key}
    number = remote_jid.split("@")[0] if "@" in remote_jid else remote_jid

    results = []
    for chunk in _chunk_text(_markdown_to_whatsapp(message_text)):
        payload = {
            "number": number,
            "text": chunk,                               # v2
            "textMessage": {"text": chunk},              # v1
            "options": {"delay": 800, "presence": "composing", "linkPreview": False},
        }
        sent, last_error = False, None
        for attempt in range(3):
            try:
                resp = requests.post(endpoint, json=payload, headers=headers, timeout=15)
                if resp.status_code in (200, 201):
                    sent = True
                    break
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                if 400 <= resp.status_code < 500:
                    break  # don't retry client errors
            except requests.RequestException as exc:
                last_error = str(exc)
            time.sleep(0.5 * (attempt + 1))
        if sent:
            results.append({"success": True})
        else:
            logger.error("WhatsApp send failed to %s: %s", number, last_error)
            results.append({"success": False, "error": last_error})

    ok = all(r.get("success") for r in results) and bool(results)
    return {"success": ok, "parts": len(results), "results": results}
