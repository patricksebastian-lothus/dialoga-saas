"""
CRUD de conexoes WhatsApp + envio de mensagem de teste (Fase 3).

Montado em main.py com prefixo /api/whatsapp/connections.
Segue o padrao do projeto: Depends(get_db) + Depends(get_current_user) (retorna User),
filtros por owner_id, respostas com model_validate / from_attributes.

Seguranca:
- Token e' CRIPTOGRAFADO (Fernet) antes de salvar; nunca retornado nas respostas.
- Toda query filtra por owner_id == current_user.id (anti-IDOR); 404 quando nao e' do dono.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Flow
from ..models_whatsapp import WhatsAppConnection, WhatsAppInboundEvent, WhatsAppOutboundMessage, WhatsAppContactState
from ..schemas_whatsapp import (
    WhatsAppConnectionCreate, WhatsAppConnectionOut, WhatsAppSendTestRequest,
    WhatsAppAutomationPauseUpdate,
)
from ..auth import get_current_user
from ..crypto import encrypt_secret
from ..services.whatsapp_meta_service import (
    send_text_via_connection, validate_connection_token,
)
from ..services import plan_limits

logger = logging.getLogger("whatsflow.whatsapp.connections")

router = APIRouter()


def _get_owned_connection(db: Session, conn_id: int, user: User) -> WhatsAppConnection:
    conn = (
        db.query(WhatsAppConnection)
        .filter(WhatsAppConnection.id == conn_id,
                WhatsAppConnection.owner_id == user.id)
        .first()
    )
    if not conn:
        raise HTTPException(404, "Conexao nao encontrada.")
    return conn


@router.get("", response_model=list[WhatsAppConnectionOut])
def list_connections(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista as conexoes WhatsApp do usuario (sem expor tokens)."""
    conns = (
        db.query(WhatsAppConnection)
        .filter(WhatsAppConnection.owner_id == current_user.id)
        .order_by(WhatsAppConnection.created_at.desc())
        .all()
    )
    return [WhatsAppConnectionOut.model_validate(c) for c in conns]


@router.post("", response_model=WhatsAppConnectionOut)
def create_connection(
    payload: WhatsAppConnectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cria/atualiza a conexao Meta do usuario para um phone_number_id.
    - Valida o token contra a Graph API (feedback imediato).
    - Criptografa o token antes de salvar.
    - phone_number_id e' unico por provider (UNIQUE no banco).
    """
    # valida limite de conexões somente ao criar nova conexão; upsert existente é permitido
    existing_same = (
        db.query(WhatsAppConnection)
        .filter(WhatsAppConnection.provider == "meta",
                WhatsAppConnection.phone_number_id == payload.phone_number_id,
                WhatsAppConnection.owner_id == current_user.id)
        .first()
    )
    if existing_same is None:
        plan_limits.assert_can_create_whatsapp_connection(db, current_user)

    # valida flow se enviado
    if payload.flow_id is not None:
        flow = (
            db.query(Flow)
            .filter(Flow.id == payload.flow_id, Flow.owner_id == current_user.id)
            .first()
        )
        if not flow:
            raise HTTPException(404, "Fluxo nao encontrado.")

    # impede roubo de numero ja' usado por OUTRO usuario
    clash = (
        db.query(WhatsAppConnection)
        .filter(WhatsAppConnection.provider == "meta",
                WhatsAppConnection.phone_number_id == payload.phone_number_id,
                WhatsAppConnection.owner_id != current_user.id)
        .first()
    )
    if clash:
        raise HTTPException(409, "Este phone_number_id ja' esta vinculado a outra conta.")

    # valida credenciais na Meta (nao bloqueia salvar, mas informa)
    validation = validate_connection_token(payload.access_token, payload.phone_number_id)

    # upsert: se ja' existe uma conexao deste usuario para este phone_number_id, atualiza
    conn = (
        db.query(WhatsAppConnection)
        .filter(WhatsAppConnection.provider == "meta",
                WhatsAppConnection.phone_number_id == payload.phone_number_id,
                WhatsAppConnection.owner_id == current_user.id)
        .first()
    )
    if conn is None:
        conn = WhatsAppConnection(owner_id=current_user.id, provider="meta",
                                  phone_number_id=payload.phone_number_id)
        db.add(conn)

    conn.display_name = payload.display_name
    conn.waba_id = payload.waba_id
    conn.flow_id = payload.flow_id
    conn.access_token_enc = encrypt_secret(payload.access_token)
    conn.access_token_last4 = payload.access_token[-4:]

    if validation.get("ok"):
        conn.status = "connected"
        conn.phone_number = validation.get("display_phone_number") or conn.phone_number
        if not conn.display_name:
            conn.display_name = validation.get("verified_name")
        conn.last_error = None
    else:
        conn.status = "error"
        conn.last_error = validation.get("hint") or validation.get("error") or "Falha na validacao do token."

    db.commit()
    db.refresh(conn)
    return WhatsAppConnectionOut.model_validate(conn)


def _purge_connection(db: Session, conn: WhatsAppConnection) -> None:
    """Apaga filhos com FK e a conexao. Nao chama Evolution (evita timeout/404)."""
    cid = conn.id
    db.query(WhatsAppContactState).filter(WhatsAppContactState.connection_id == cid).delete(synchronize_session=False)
    db.query(WhatsAppOutboundMessage).filter(WhatsAppOutboundMessage.connection_id == cid).delete(synchronize_session=False)
    db.query(WhatsAppInboundEvent).filter(WhatsAppInboundEvent.connection_id == cid).delete(synchronize_session=False)
    db.delete(conn)
    db.commit()


@router.delete("/{conn_id}")
def delete_connection(
    conn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conn = _get_owned_connection(db, conn_id, current_user)
    _purge_connection(db, conn)
    return {"ok": True}


@router.post("/{conn_id}/remove")
def remove_connection(
    conn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Alias POST: alguns proxies/browsers quebram DELETE e o fetch vira 'nao conectou'."""
    conn = _get_owned_connection(db, conn_id, current_user)
    _purge_connection(db, conn)
    return {"ok": True}


@router.post("/{conn_id}/automation-paused", response_model=WhatsAppConnectionOut)
def set_automation_paused(
    conn_id: int,
    payload: WhatsAppAutomationPauseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pausa/retoma a automação da conexão inteira.

    Quando pausada, o webhook registra mensagens, mas não aciona o bot para nenhum contato
    desta conexão. É diferente da pausa por lead (handoff individual).
    """
    conn = _get_owned_connection(db, conn_id, current_user)
    conn.automation_paused = bool(payload.paused)
    db.commit()
    db.refresh(conn)
    return WhatsAppConnectionOut.model_validate(conn)


@router.post("/{conn_id}/send-test")
def send_test(
    conn_id: int,
    payload: WhatsAppSendTestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Envia uma mensagem de teste usando a conexao.
    Atualiza last_error/status conforme o resultado (ex.: token invalido -> status=error).
    """
    conn = _get_owned_connection(db, conn_id, current_user)
    from ..services import evolution_service as evo_svc

    if conn.provider == "evolution":
        if not conn.evolution_instance_name:
            raise HTTPException(400, "Conexao Evolution sem instancia.")
        result = evo_svc.send_text(conn.evolution_instance_name, payload.to, payload.text)
    else:
        result = send_text_via_connection(conn, payload.to, payload.text)

    if result.get("ok"):
        if conn.status != "connected":
            conn.status = "connected"
        conn.last_error = None
        db.commit()
        return {"ok": True, "provider_message_id": result.get("provider_message_id")}

    msg = result.get("hint") or result.get("error") or "Falha desconhecida."
    if "Application not found" in str(msg) or "HTTP 404" in str(msg):
        conn.status = "error"
        msg = (
            "Instancia nao encontrada na Evolution (Application not found). "
            "Apague esta conexao e crie outra pelo QR Code."
        )
    if result.get("error_code") == 190:
        conn.status = "error"
    conn.last_error = msg
    db.commit()
    raise HTTPException(502, msg)


# ============================================================ #
# Evolution API (WhatsApp NAO-OFICIAL / QR Code) — Fase 5
# ============================================================ #
import uuid as _uuid
from ..config import settings as _settings
from ..crypto import encrypt_secret as _encrypt_secret
from ..schemas_whatsapp import EvolutionConnectionCreate
from ..services import evolution_service as _evo
from ..models_whatsapp import WhatsAppContactState as _WAContactState


def _evo_webhook_url() -> str:
    """URL publica do webhook da Evolution (aponta para o backend do dIAloga+)."""
    base = (_settings.public_base_url or "").rstrip("/")
    return f"{base}/webhook/whatsapp/evo"


@router.post("/evolution", response_model=WhatsAppConnectionOut)
def create_evolution_connection(
    payload: EvolutionConnectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cria uma conexao via QR Code (Evolution). Cria a instancia na Evolution com webhook
    de volta pro dIAloga+, e retorna a conexao (o QR e' obtido no endpoint /qrcode).
    """
    if not _settings.evolution_enabled:
        raise HTTPException(400, "Conexao via QR Code (Evolution) nao esta habilitada.")
    plan_limits.assert_can_create_whatsapp_connection(db, current_user)
    if payload.flow_id is not None:
        flow = db.query(Flow).filter(Flow.id == payload.flow_id, Flow.owner_id == current_user.id).first()
        if not flow:
            raise HTTPException(404, "Fluxo nao encontrado.")

    instance_name = f"diaplus-{current_user.id}-{_uuid.uuid4().hex[:8]}"
    webhook_secret = _evo.gen_webhook_secret()

    result = _evo.create_instance(instance_name, _evo_webhook_url(), webhook_secret)
    if not result.get("ok"):
        raise HTTPException(502, f"Falha ao criar instancia na Evolution: {result.get('error')}")

    conn = WhatsAppConnection(
        owner_id=current_user.id,
        provider="evolution",
        status="connecting",
        display_name=payload.display_name,
        flow_id=payload.flow_id,
        evolution_instance_name=instance_name,
        webhook_secret_enc=_encrypt_secret(webhook_secret),
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return WhatsAppConnectionOut.model_validate(conn)


@router.get("/{conn_id}/qrcode")
def get_evolution_qrcode(
    conn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retorna o QR Code (base64) para conectar o WhatsApp.
    Primeiro tenta o cache (vindo do webhook QRCODE_UPDATED); se nao houver, pede um novo
    a Evolution via /instance/connect.
    """
    conn = _get_owned_connection(db, conn_id, current_user)
    if conn.provider != "evolution":
        raise HTTPException(400, "Esta conexao nao e' do tipo QR Code.")

    # 1) cache do webhook
    holder = (
        db.query(_WAContactState)
        .filter(_WAContactState.connection_id == conn.id, _WAContactState.wa_id == "__qr__")
        .first()
    )
    cached_qr = (holder.context or {}).get("qrcode_base64") if holder else None

    # 2) pede um novo/estado atual
    res = _evo.connect_instance(conn.evolution_instance_name)
    qr = (res.get("qrcode_base64") if res.get("ok") else None) or cached_qr

    # atualiza status atual
    st = _evo.connection_state(conn.evolution_instance_name)
    if st.get("ok"):
        mapping = {"open": "connected", "connecting": "connecting", "close": "disconnected"}
        conn.status = mapping.get(st.get("state"), conn.status)
        db.commit()

    return {
        "ok": True,
        "status": conn.status,
        "qrcode_base64": qr,
        "pairing_code": res.get("pairing_code") if res.get("ok") else None,
        "connected": conn.status == "connected",
    }


@router.get("/{conn_id}/status")
def get_evolution_status(
    conn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Consulta o status atual da conexao (para a UI fazer polling)."""
    conn = _get_owned_connection(db, conn_id, current_user)
    if conn.provider == "evolution":
        st = _evo.connection_state(conn.evolution_instance_name)
        if st.get("ok"):
            mapping = {"open": "connected", "connecting": "connecting", "close": "disconnected"}
            conn.status = mapping.get(st.get("state"), conn.status)
            db.commit()
    return {"ok": True, "status": conn.status, "connected": conn.status == "connected"}
