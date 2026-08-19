"""
Servico de integracao com a Evolution API (WhatsApp NAO-OFICIAL / QR Code).

Fala com a instancia Evolution do usuario (hospedada no Railway) para:
- criar instancia (com webhook apontando de volta pro dIAloga+)
- gerar/obter QR Code
- checar estado da conexao
- enviar mensagens de texto

Config global (env vars):
- EVOLUTION_BASE_URL: URL da Evolution (ex: https://xxxx.up.railway.app)
- EVOLUTION_GLOBAL_API_KEY: a AUTHENTICATION_API_KEY da Evolution

Cada WhatsAppConnection provider='evolution' guarda:
- evolution_instance_name: nome unico da instancia
- webhook_secret_enc: segredo p/ autenticar o webhook que a Evolution manda de volta

Sincrono (httpx.Client) — casa com o resto do projeto.
"""
import logging
import secrets
from typing import Any, Dict, Optional

import httpx

from ..config import settings

logger = logging.getLogger("whatsflow.evolution")


def _base_url() -> str:
    return (settings.evolution_base_url or "").rstrip("/")


def _headers(api_key: Optional[str] = None) -> dict:
    return {
        "apikey": api_key or settings.evolution_global_api_key,
        "Content-Type": "application/json",
    }


def _configured() -> bool:
    return bool(_base_url() and settings.evolution_global_api_key)


def gen_webhook_secret() -> str:
    """Gera um segredo para autenticar o webhook da Evolution (header Authorization)."""
    return secrets.token_urlsafe(32)


def create_instance(instance_name: str, webhook_url: str, webhook_secret: str) -> Dict[str, Any]:
    """
    Cria uma instancia Evolution ja' configurando o webhook de volta para o dIAloga+.
    Retorna {ok, data?/error?}.
    """
    if not _configured():
        return {"ok": False, "error": "Evolution nao configurada (EVOLUTION_BASE_URL / API_KEY)."}
    url = f"{_base_url()}/instance/create"
    body = {
        "instanceName": instance_name,
        "qrcode": True,
        "integration": "WHATSAPP-BAILEYS",
        "groupsIgnore": True,          # ignora mensagens de grupo
        "rejectCall": True,            # rejeita chamadas automaticamente
        "webhook": {
            "url": webhook_url,
            "byEvents": False,
            "base64": True,            # QR vem em base64 (facil de exibir)
            "headers": {
                "Authorization": f"Bearer {webhook_secret}",
                "Content-Type": "application/json",
            },
            "events": ["QRCODE_UPDATED", "MESSAGES_UPSERT", "CONNECTION_UPDATE"],
        },
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, headers=_headers(), json=body)
    except Exception as exc:
        return {"ok": False, "error": f"Erro de rede ao criar instancia: {type(exc).__name__}"}
    if r.status_code in (200, 201):
        return {"ok": True, "data": r.json()}
    # instancia ja existe? tenta seguir mesmo assim
    txt = r.text[:300]
    if r.status_code in (403, 409) and "already" in txt.lower():
        return {"ok": True, "data": {"note": "instancia ja existia"}}
    return {"ok": False, "error": f"HTTP {r.status_code}: {txt}"}


def connect_instance(instance_name: str) -> Dict[str, Any]:
    """
    Obtem o QR Code (ou status) para conectar. Retorna {ok, qrcode_base64?, pairing_code?, state?}.
    A Evolution v2 retorna 'base64' (imagem do QR) e/ou 'code'/'pairingCode'.
    """
    if not _configured():
        return {"ok": False, "error": "Evolution nao configurada."}
    url = f"{_base_url()}/instance/connect/{instance_name}"
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(url, headers=_headers())
    except Exception as exc:
        return {"ok": False, "error": f"Erro de rede: {type(exc).__name__}"}
    if r.status_code != 200:
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}
    data = r.json()
    # A resposta varia: pode vir {base64, code, pairingCode} ou {instance:{state}}
    qr = data.get("base64") or (data.get("qrcode") or {}).get("base64")
    return {
        "ok": True,
        "qrcode_base64": qr,
        "pairing_code": data.get("pairingCode") or data.get("code"),
        "raw": data,
    }


def connection_state(instance_name: str) -> Dict[str, Any]:
    """Consulta o estado atual da conexao. Retorna {ok, state} — state: open|connecting|close."""
    if not _configured():
        return {"ok": False, "error": "Evolution nao configurada."}
    url = f"{_base_url()}/instance/connectionState/{instance_name}"
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(url, headers=_headers())
    except Exception as exc:
        return {"ok": False, "error": f"Erro de rede: {type(exc).__name__}"}
    if r.status_code != 200:
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
    data = r.json()
    state = (data.get("instance") or {}).get("state") or data.get("state")
    return {"ok": True, "state": state, "raw": data}


def delete_instance(instance_name: str) -> Dict[str, Any]:
    """Remove a instancia da Evolution (logout + delete)."""
    if not _configured():
        return {"ok": False, "error": "Evolution nao configurada."}
    try:
        with httpx.Client(timeout=8.0) as client:
            client.delete(f"{_base_url()}/instance/logout/{instance_name}", headers=_headers())
            r = client.delete(f"{_base_url()}/instance/delete/{instance_name}", headers=_headers())
    except Exception as exc:
        return {"ok": False, "error": f"Erro de rede: {type(exc).__name__}"}
    return {"ok": r.status_code in (200, 201, 404)}


def send_text(instance_name: str, to_number: str, text: str) -> Dict[str, Any]:
    """
    Envia texto por uma instancia Evolution.
    to_number: numero com DDI, sem @ (ex: 5521999998888). A Evolution aceita assim.
    Retorna {ok, provider_message_id?/error?}.
    """
    if not _configured():
        return {"ok": False, "error": "Evolution nao configurada."}
    url = f"{_base_url()}/message/sendText/{instance_name}"
    body = {"number": to_number, "text": text}
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, headers=_headers(), json=body)
    except httpx.TimeoutException:
        return {"ok": False, "error": "Timeout ao enviar pela Evolution."}
    except Exception as exc:
        return {"ok": False, "error": f"Erro de rede: {type(exc).__name__}"}
    if r.status_code in (200, 201):
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        wamid = None
        try:
            wamid = (data.get("key") or {}).get("id")
        except Exception:
            pass
        return {"ok": True, "provider_message_id": wamid, "response": data}
    return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}


def get_base64_from_media_message(instance_name: str, message_key: dict, convert_to_mp4: bool = True) -> Dict[str, Any]:
    """Busca base64 de mídia recebida pela Evolution.

    Evolution v2: POST /chat/getBase64FromMediaMessage/{instance}
    Retorna {ok, base64, mimetype, media_type, file_name, raw} ou {ok:false,error}.
    """
    if not _configured():
        return {"ok": False, "error": "Evolution nao configurada."}
    msg_id = (message_key or {}).get("id")
    if not msg_id:
        return {"ok": False, "error": "message.key.id ausente para baixar midia."}
    url = f"{_base_url()}/chat/getBase64FromMediaMessage/{instance_name}"
    body = {
        "message": {"key": message_key},
        "convertToMp4": bool(convert_to_mp4),
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(url, headers=_headers(), json=body)
    except Exception as exc:
        return {"ok": False, "error": f"Erro de rede ao baixar midia: {type(exc).__name__}"}
    if r.status_code not in (200, 201):
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}
    data = r.json()
    b64 = data.get("base64") or data.get("media") or data.get("data")
    if isinstance(b64, str) and "," in b64 and b64.strip().startswith("data:"):
        b64 = b64.split(",", 1)[1]
    return {
        "ok": bool(b64),
        "base64": b64,
        "mimetype": data.get("mimetype") or data.get("mimeType") or "audio/mp4",
        "media_type": data.get("mediaType") or data.get("media_type"),
        "file_name": data.get("fileName") or data.get("file_name"),
        "raw": data,
        "error": None if b64 else "Resposta sem base64.",
    }


# --------------------- Parsing do webhook recebido --------------------- #
def normalize_jid(jid: Optional[str]) -> Optional[str]:
    """Extrai o numero de um JID do WhatsApp (ex: 5521999@s.whatsapp.net -> 5521999)."""
    if not jid:
        return None
    return jid.split("@", 1)[0].split(":", 1)[0]


def extract_text_from_message(message: dict) -> Optional[str]:
    """Extrai o texto de um objeto message do Baileys (varios formatos possiveis)."""
    if not message:
        return None
    if message.get("conversation"):
        return message["conversation"]
    ext = message.get("extendedTextMessage")
    if ext and ext.get("text"):
        return ext["text"]
    # botoes / listas
    btn = message.get("buttonsResponseMessage")
    if btn:
        return btn.get("selectedButtonId") or btn.get("selectedDisplayText")
    lst = message.get("listResponseMessage")
    if lst:
        sr = lst.get("singleSelectReply") or {}
        return sr.get("selectedRowId") or lst.get("title")
    return None


def is_audio_message(message: dict) -> bool:
    """Detecta áudio/PTT em payload Baileys."""
    if not message:
        return False
    return bool(message.get("audioMessage"))


def extract_audio_mimetype(message: dict) -> Optional[str]:
    audio = (message or {}).get("audioMessage") or {}
    return audio.get("mimetype") or audio.get("mimeType")
