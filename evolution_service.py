import os
import logging
import requests
from typing import Dict, Any, Optional

from database import get_db, get_settings, normalize_phone

logger = logging.getLogger(__name__)

def parse_evolution_webhook_payload(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Parses Evolution API v1 & v2 webhook payload.
    Extracts sender phone, message text, sender name, and message id.
    """
    try:
        event = payload.get("event")
        # Handle messages.upsert / MESSAGES_UPSERT
        if event and "message" not in event.lower():
            return None

        data = payload.get("data", {})
        key = data.get("key", {})
        
        # Don't process messages sent by the bot itself
        if key.get("fromMe", False):
            return None

        remote_jid = key.get("remoteJid", "")
        if not remote_jid or "@g.us" in remote_jid: # Ignore group messages by default
            return None

        phone = remote_jid.split("@")[0]
        sender_name = data.get("pushName", "WhatsApp User")

        # Extract message text from various WhatsApp message structures
        message_obj = data.get("message", {})
        text = ""
        if "conversation" in message_obj:
            text = message_obj["conversation"]
        elif "extendedTextMessage" in message_obj:
            text = message_obj["extendedTextMessage"].get("text", "")
        elif "buttonsResponseMessage" in message_obj:
            text = message_obj["buttonsResponseMessage"].get("selectedButtonId", "")
        elif "listResponseMessage" in message_obj:
            text = message_obj["listResponseMessage"].get("singleSelectReply", {}).get("selectedRowId", "")

        if not text or not text.strip():
            return None

        return {
            "phone": normalize_phone(phone),
            "remote_jid": remote_jid,
            "sender_name": sender_name,
            "text": text.strip(),
            "message_id": key.get("id")
        }
    except Exception as e:
        logger.error(f"Error parsing Evolution API webhook: {str(e)}")
        return None


def send_whatsapp_message(
    remote_jid: str, 
    message_text: str, 
    custom_instance: Optional[str] = None
) -> Dict[str, Any]:
    """
    Sends a message via Evolution API REST endpoint.
    POST /message/sendText/{instance}
    """
    db = get_db()
    try:
        settings = get_settings(db)
        base_url = (settings.evolution_api_url or "http://localhost:8080").rstrip("/")
        api_key = settings.evolution_api_key or "B6D711FCDE4D4FD5936544120E713976"
        instance = custom_instance or settings.evolution_instance_name or "VendingBot"

        endpoint = f"{base_url}/message/sendText/{instance}"
        headers = {
            "Content-Type": "application/json",
            "apikey": api_key
        }

        # Evolution API expects number or remoteJid
        number = remote_jid.replace("@s.whatsapp.net", "") if "@" in remote_jid else remote_jid
        payload = {
            "number": number,
            "options": {
                "delay": 1200,
                "presence": "composing",
                "linkPreview": False
            },
            "textMessage": {
                "text": message_text
            }
        }

        response = requests.post(endpoint, json=payload, headers=headers, timeout=10)
        return {
            "status_code": response.status_code,
            "success": response.status_code in [200, 201],
            "response": response.json() if response.headers.get("content-type") == "application/json" else response.text
        }
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message via Evolution API: {str(e)}")
        return {
            "status_code": 500,
            "success": False,
            "error": str(e)
        }
    finally:
        db.close()
