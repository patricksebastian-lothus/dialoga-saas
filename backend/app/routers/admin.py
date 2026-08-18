"""
Fase E.1 — Painel Admin básico.

Acesso permitido quando:
- User.is_admin=True no banco; OU
- email do usuário está em ADMIN_EMAILS (env var, separado por vírgula).
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import Appointment, BillingWebhookEvent, CalendarConnection, Conversation, CrmPipeline, CrmPipelineStage, CrmTag, CrmTask, CustomField, CustomFieldValue, Flow, Lead, LeadNote, Message, PendingBillingAccount, QuickReply, ROISettings, Subscription, User
from ..models_rag import AISettings, KnowledgeBase, KnowledgeChunk
from ..models_whatsapp import WhatsAppConnection, WhatsAppInboundEvent, WhatsAppOutboundMessage, WhatsAppContactState
from ..services import plan_limits, billing_service

router = APIRouter()


class AdminUserUpdate(BaseModel):
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    plan: Optional[str] = Field(None, max_length=50)


class PendingBillingClaimRequest(BaseModel):
    user_id: Optional[int] = None


def _admin_email_set() -> set[str]:
    raw = getattr(settings, "admin_emails", "") or ""
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def is_admin_user(user: User) -> bool:
    return bool(getattr(user, "is_admin", False)) or (user.email or "").lower() in _admin_email_set()


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not is_admin_user(current_user):
        raise HTTPException(403, "Acesso restrito ao administrador.")
    return current_user


def _user_summary(db: Session, user: User) -> dict:
    flows_count = db.query(Flow).filter(Flow.owner_id == user.id).count()
    leads_count = db.query(Lead).filter(Lead.owner_id == user.id).count()
    real_leads_count = db.query(Lead).filter(Lead.owner_id == user.id, Lead.source != "simulator").count()
    connections_count = db.query(WhatsAppConnection).filter(WhatsAppConnection.owner_id == user.id).count()
    appointments_count = db.query(Appointment).filter(Appointment.owner_id == user.id).count()
    kb_count = db.query(KnowledgeBase).filter(KnowledgeBase.owner_id == user.id).count()
    ai = db.query(AISettings).filter(AISettings.owner_id == user.id).first()
    return {
        "id": user.id,
        "email": user.email,
        "company_name": user.company_name,
        "full_name": user.full_name,
        "phone": user.phone,
        "plan": user.plan,
        "is_active": user.is_active,
        "is_admin": bool(getattr(user, "is_admin", False)) or (user.email or "").lower() in _admin_email_set(),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "flows_count": flows_count,
        "leads_count": leads_count,
        "real_leads_count": real_leads_count,
        "connections_count": connections_count,
        "appointments_count": appointments_count,
        "knowledge_bases_count": kb_count,
        "monthly_ai_used": ai.monthly_ai_used if ai else 0,
        "monthly_ai_limit": ai.monthly_ai_limit if ai else 0,
        "plan_limits": plan_limits.limits_for(user),
    }


def _pending_summary(p: PendingBillingAccount) -> dict:
    return {
        "id": p.id,
        "provider": p.provider,
        "external_id": p.external_id,
        "buyer_email": p.buyer_email,
        "plan": p.plan,
        "status": p.status,
        "product_name": p.product_name,
        "claimed_user_id": p.claimed_user_id,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "claimed_at": p.claimed_at.isoformat() if p.claimed_at else None,
    }


def _subscription_summary(db: Session, sub: Subscription) -> dict:
    user = db.query(User).filter(User.id == sub.owner_id).first()
    return {
        "id": sub.id,
        "owner_id": sub.owner_id,
        "user_email": user.email if user else None,
        "company_name": user.company_name if user else None,
        "provider": sub.provider,
        "external_id": sub.external_id,
        "plan": sub.plan,
        "status": sub.status,
        "buyer_email": sub.buyer_email,
        "product_name": sub.product_name,
        "started_at": sub.started_at.isoformat() if sub.started_at else None,
        "canceled_at": sub.canceled_at.isoformat() if sub.canceled_at else None,
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
        "updated_at": sub.updated_at.isoformat() if sub.updated_at else None,
    }


def _billing_event_summary(ev) -> dict:
    return {
        "id": ev.id,
        "provider": ev.provider,
        "external_event_id": ev.external_event_id,
        "event_type": ev.event_type,
        "buyer_email": ev.buyer_email,
        "status": ev.status,
        "error": ev.error,
        "received_at": ev.received_at.isoformat() if ev.received_at else None,
        "processed_at": ev.processed_at.isoformat() if ev.processed_at else None,
    }


def _health_item(key: str, label: str, status: str, message: str, *, secret: bool = False) -> dict:
    return {"key": key, "label": label, "status": status, "message": message, "secret": secret}


def _present(value: str | None) -> bool:
    return bool(str(value or "").strip())


def _readiness_check(key: str, label: str, ok: bool, message: str, *, required: bool = True) -> dict:
    return {
        "key": key,
        "label": label,
        "ok": bool(ok),
        "status": "ok" if ok else ("error" if required else "warn"),
        "required": required,
        "message": message,
    }


def _user_beta_readiness(db: Session, user: User) -> dict:
    """Mede se um cliente está pronto para entrar em beta fechado.

    Usa apenas dados já existentes. Não cria dependência nova nem altera schema.
    """
    active_flows = db.query(Flow).filter(Flow.owner_id == user.id, Flow.active == True).count()  # noqa: E712
    total_flows = db.query(Flow).filter(Flow.owner_id == user.id).count()
    connected_connections = db.query(WhatsAppConnection).filter(
        WhatsAppConnection.owner_id == user.id,
        WhatsAppConnection.status == "connected",
    ).count()
    paused_connections = db.query(WhatsAppConnection).filter(
        WhatsAppConnection.owner_id == user.id,
        WhatsAppConnection.automation_paused == True,  # noqa: E712
    ).count()
    real_leads = db.query(Lead).filter(Lead.owner_id == user.id, Lead.source != "simulator").count()
    appointments = db.query(Appointment).filter(Appointment.owner_id == user.id).count()
    calendar_connected = db.query(CalendarConnection).filter(
        CalendarConnection.owner_id == user.id,
        CalendarConnection.status == "connected",
    ).count()
    kb_ids = [x[0] for x in db.query(KnowledgeBase.id).filter(KnowledgeBase.owner_id == user.id).all()]
    kb_count = len(kb_ids)
    chunks = 0
    if kb_ids:
        chunks = db.query(KnowledgeChunk).filter(KnowledgeChunk.knowledge_base_id.in_(kb_ids)).count()
    sub_active = db.query(Subscription).filter(Subscription.owner_id == user.id, Subscription.status == "active").count()

    checks = [
        _readiness_check(
            "account_active", "Conta ativa", bool(user.is_active),
            "Conta ativa." if user.is_active else "Ative a conta antes de incluir no beta.",
        ),
        _readiness_check(
            "flow_active", "Fluxo publicado", active_flows > 0,
            f"{active_flows} fluxo(s) ativo(s)." if active_flows else "Criar ou ativar pelo menos um fluxo.",
        ),
        _readiness_check(
            "whatsapp_connected", "WhatsApp conectado", connected_connections > 0,
            f"{connected_connections} conexão(ões) conectada(s)." if connected_connections else "Conectar um WhatsApp e validar QR/status.",
        ),
        _readiness_check(
            "knowledge_indexed", "Base de IA indexada", chunks > 0,
            f"{kb_count} base(s), {chunks} trecho(s) indexado(s)." if chunks else "Subir conhecimento e indexar a base para testar IA/RAG.",
        ),
        _readiness_check(
            "real_lead_test", "Teste real recebido", real_leads > 0,
            f"{real_leads} lead(s) real(is) recebido(s)." if real_leads else "Enviar mensagem real pelo WhatsApp e confirmar lead/conversa.",
        ),
        _readiness_check(
            "automation_unpaused", "Automação liberada", paused_connections == 0,
            "Nenhuma conexão pausada." if paused_connections == 0 else f"{paused_connections} conexão(ões) com automação pausada.",
            required=False,
        ),
        _readiness_check(
            "calendar_connected", "Agenda conectada", calendar_connected > 0,
            "Google Calendar conectado." if calendar_connected else "Conectar Google Calendar se o nicho usar agendamento.",
            required=False,
        ),
        _readiness_check(
            "billing_active", "Assinatura/billing", sub_active > 0,
            "Assinatura ativa encontrada." if sub_active else "Para beta pode ser manual, mas antes de venda validar billing.",
            required=False,
        ),
    ]

    required_checks = [c for c in checks if c["required"]]
    required_ok = sum(1 for c in required_checks if c["ok"])
    optional_ok = sum(1 for c in checks if (not c["required"] and c["ok"]))
    score = round(((required_ok / max(len(required_checks), 1)) * 80) + ((optional_ok / 3) * 20))
    mandatory_ready = all(c["ok"] for c in required_checks)
    warnings = [c for c in checks if (not c["required"] and not c["ok"])]

    if mandatory_ready and not warnings:
        status = "ready"
        status_label = "Pronto para beta"
    elif mandatory_ready:
        status = "ready_with_warnings"
        status_label = "Pronto com avisos"
    elif bool(user.is_active) and (active_flows > 0 or connected_connections > 0):
        status = "partial"
        status_label = "Preparação parcial"
    else:
        status = "setup"
        status_label = "Setup inicial"

    next_actions = [c["message"] for c in checks if not c["ok"]][:4]
    if not next_actions:
        next_actions = ["Executar roteiro de beta com conversa real, áudio, handoff, agenda e ROI."]

    return {
        "user_id": user.id,
        "email": user.email,
        "company_name": user.company_name,
        "full_name": user.full_name,
        "plan": user.plan,
        "score": score,
        "status": status,
        "status_label": status_label,
        "next_actions": next_actions,
        "metrics": {
            "flows_total": total_flows,
            "active_flows": active_flows,
            "connected_connections": connected_connections,
            "real_leads": real_leads,
            "knowledge_bases": kb_count,
            "knowledge_chunks": chunks,
            "appointments": appointments,
            "calendar_connected": calendar_connected,
            "active_subscriptions": sub_active,
        },
        "checks": checks,
    }


@router.get("/system-health")
def admin_system_health(admin: User = Depends(require_admin)):
    """Checklist de saúde para produção/go-live.

    Não expõe valores secretos; apenas indica ausente/configurado e alerta riscos.
    """
    items = []

    default_secret = "chave-padrao-desenvolvimento" in (settings.secret_key or "")
    items.append(_health_item(
        "secret_key", "SECRET_KEY", "error" if default_secret else "ok",
        "Troque a SECRET_KEY padrão antes de produção." if default_secret else "SECRET_KEY configurada.",
        secret=True,
    ))
    items.append(_health_item(
        "database_url", "DATABASE_URL", "ok" if _present(settings.database_url) else "error",
        "Banco configurado." if _present(settings.database_url) else "DATABASE_URL ausente.",
        secret=True,
    ))
    cors = settings.cors_origins or ""
    items.append(_health_item(
        "cors_origins", "CORS_ORIGINS", "warn" if "localhost" in cors and "dialoga-frontend" not in cors else "ok",
        "CORS ainda parece conter apenas localhost; confirme domínio de produção." if "localhost" in cors and "dialoga-frontend" not in cors else "CORS configurado.",
    ))
    items.append(_health_item(
        "wa_fernet_keys", "WA_FERNET_KEYS", "ok" if _present(settings.wa_fernet_keys) else "error",
        "Chave Fernet configurada." if _present(settings.wa_fernet_keys) else "WA_FERNET_KEYS ausente: tokens não podem ser criptografados.",
        secret=True,
    ))

    # Evolution / QR
    if settings.evolution_enabled:
        ok = _present(settings.evolution_base_url) and _present(settings.evolution_global_api_key) and _present(settings.public_base_url)
        items.append(_health_item(
            "evolution", "Evolution API / QR", "ok" if ok else "error",
            "Evolution configurada." if ok else "Evolution habilitada, mas faltam BASE_URL, API_KEY ou PUBLIC_BASE_URL.",
            secret=True,
        ))
    else:
        items.append(_health_item("evolution", "Evolution API / QR", "warn", "Evolution desabilitada."))

    # Gemini
    items.append(_health_item(
        "gemini", "Gemini IA", "ok" if _present(settings.gemini_api_key) else "warn",
        "GEMINI_API_KEY configurada." if _present(settings.gemini_api_key) else "GEMINI_API_KEY ausente: IA/RAG/áudio podem falhar.",
        secret=True,
    ))
    if (settings.gemini_chat_model or "") == "gemini-2.0-flash":
        items.append(_health_item("gemini_model", "GEMINI_CHAT_MODEL", "warn", "Modelo padrão antigo detectado. Recomenda-se gemini-2.5-flash ou flash-lite."))
    else:
        items.append(_health_item("gemini_model", "GEMINI_CHAT_MODEL", "ok", f"Modelo: {settings.gemini_chat_model}"))

    # Google Calendar
    if settings.google_calendar_enabled:
        ok = _present(settings.google_client_id) and _present(settings.google_client_secret)
        items.append(_health_item(
            "google_calendar", "Google Calendar", "ok" if ok else "error",
            "Google Calendar habilitado e credenciais configuradas." if ok else "Google Calendar habilitado, mas faltam CLIENT_ID/SECRET.",
            secret=True,
        ))
    else:
        items.append(_health_item("google_calendar", "Google Calendar", "warn", "Google Calendar desabilitado."))

    # Billing
    if settings.billing_enabled:
        provider = (settings.billing_provider or "manual").lower()
        token_ok = True
        if provider == "hotmart":
            token_ok = _present(settings.hotmart_webhook_token)
        elif provider == "eduzz":
            token_ok = _present(settings.eduzz_webhook_token)
        items.append(_health_item(
            "billing", "Billing", "ok" if token_ok else "warn",
            f"Billing habilitado ({provider})." if token_ok else f"Billing habilitado ({provider}), mas token de webhook não configurado.",
            secret=True,
        ))
    else:
        items.append(_health_item("billing", "Billing", "warn", "Billing desabilitado; acesso ainda depende de controle manual/webhooks em teste."))

    # Meta
    if settings.whatsapp_meta_enabled:
        meta_ok = _present(settings.meta_app_secret)
        items.append(_health_item(
            "meta", "Meta Cloud API", "warn" if meta_ok else "error",
            "Meta configurada, mas lembre de Business Verification e erro 130497 para Brasil." if meta_ok else "Meta habilitada, mas META_APP_SECRET ausente.",
            secret=True,
        ))
    else:
        items.append(_health_item("meta", "Meta Cloud API", "warn", "Meta Cloud API desabilitada ou em shadow/teste."))

    # Admin / Domínio / go-live
    items.append(_health_item(
        "admin_emails", "ADMIN_EMAILS", "ok" if _present(settings.admin_emails) else "warn",
        "ADMIN_EMAILS configurado." if _present(settings.admin_emails) else "ADMIN_EMAILS ausente: primeiro admin pode depender de is_admin no banco.",
    ))
    render_domain = "onrender.com" in (settings.public_base_url or "") or "onrender.com" in (settings.frontend_base_url or "")
    items.append(_health_item(
        "custom_domain", "Domínio próprio", "warn" if render_domain else "ok",
        "Ainda usando domínio onrender.com. Para go-live, configurar domínio próprio e atualizar OAuth/webhooks." if render_domain else "Domínio próprio parece configurado.",
    ))
    items.append(_health_item(
        "render_plan", "Render", "warn",
        "Se estiver no plano Free, o backend dorme e pode estourar memória. Para go-live, usar plano pago.",
    ))
    items.append(_health_item(
        "legal_pages", "Termos e Privacidade", "warn" if "onrender.com" in (settings.privacy_policy_url or "") else "ok",
        f"Privacidade: {settings.privacy_policy_url} | Termos: {settings.terms_url}. Em produção, usar domínio próprio e revisar juridicamente.",
    ))
    items.append(_health_item(
        "email_official", "E-mail oficial", "warn",
        "E-mails atuais são temporários. Antes de produção, configurar domínio/e-mail oficial, SPF/DKIM/DMARC e provedor transacional.",
    ))

    counts = {"ok": 0, "warn": 0, "error": 0}
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    overall = "error" if counts["error"] else ("warn" if counts["warn"] else "ok")
    return {"overall": overall, "counts": counts, "items": items}


@router.get("/beta-readiness")
def admin_beta_readiness(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Painel de preparação para beta fechado.

    Ajuda a escolher quais contas podem testar o produto completo antes do go-live comercial.
    """
    users = db.query(User).order_by(User.created_at.desc()).limit(200).all()
    candidates = [_user_beta_readiness(db, u) for u in users]
    counts = {
        "ready": sum(1 for c in candidates if c["status"] == "ready"),
        "ready_with_warnings": sum(1 for c in candidates if c["status"] == "ready_with_warnings"),
        "partial": sum(1 for c in candidates if c["status"] == "partial"),
        "setup": sum(1 for c in candidates if c["status"] == "setup"),
    }
    ordered = sorted(candidates, key=lambda c: (c["score"], c["metrics"]["real_leads"]), reverse=True)
    return {
        "phase": "Beta fechado / go-live técnico",
        "goal": "Validar contas reais com WhatsApp, IA/RAG, Inbox, Agenda, ROI e Billing antes de vender em escala.",
        "counts": counts,
        "total_users": len(candidates),
        "top_blockers": _beta_top_blockers(candidates),
        "candidates": ordered,
    }


def _beta_top_blockers(candidates: list[dict]) -> list[dict]:
    blockers: dict[str, dict] = {}
    for candidate in candidates:
        for check in candidate.get("checks", []):
            if check.get("ok") or not check.get("required"):
                continue
            key = check["key"]
            if key not in blockers:
                blockers[key] = {"key": key, "label": check["label"], "count": 0, "message": check["message"]}
            blockers[key]["count"] += 1
    return sorted(blockers.values(), key=lambda x: x["count"], reverse=True)[:5]


@router.get("/plans")
def admin_plans(admin: User = Depends(require_admin)):
    """Tabela de limites dos planos disponíveis."""
    return plan_limits.public_plan_table()


@router.get("/overview")
def admin_overview(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    users_total = db.query(User).count()
    users_active = db.query(User).filter(User.is_active == True).count()  # noqa: E712
    return {
        "subscriptions_total": db.query(Subscription).count(),
        "subscriptions_active": db.query(Subscription).filter(Subscription.status == "active").count(),
        "pending_billing_total": db.query(PendingBillingAccount).filter(PendingBillingAccount.status == "pending").count(),
        "users_total": users_total,
        "users_active": users_active,
        "flows_total": db.query(Flow).count(),
        "leads_total": db.query(Lead).count(),
        "real_leads_total": db.query(Lead).filter(Lead.source != "simulator").count(),
        "appointments_total": db.query(Appointment).count(),
        "whatsapp_connections_total": db.query(WhatsAppConnection).count(),
        "knowledge_bases_total": db.query(KnowledgeBase).count(),
        "conversations_total": db.query(Conversation).count(),
        "admin_email_mode": bool(_admin_email_set()),
    }


@router.get("/subscriptions")
def admin_subscriptions(
    status: Optional[str] = None,
    provider: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    q = db.query(Subscription)
    if status:
        q = q.filter(Subscription.status == status)
    if provider:
        q = q.filter(Subscription.provider == provider)
    items = q.order_by(Subscription.updated_at.desc()).limit(300).all()
    return [_subscription_summary(db, s) for s in items]


@router.get("/billing-events")
def admin_billing_events(
    status: Optional[str] = None,
    provider: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    q = db.query(BillingWebhookEvent)
    if status:
        q = q.filter(BillingWebhookEvent.status == status)
    if provider:
        q = q.filter(BillingWebhookEvent.provider == provider)
    items = q.order_by(BillingWebhookEvent.received_at.desc()).limit(300).all()
    return [_billing_event_summary(e) for e in items]


@router.get("/users")
def admin_list_users(
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    query = db.query(User)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter((User.email.ilike(like)) | (User.company_name.ilike(like)))
    users = query.order_by(User.created_at.desc()).all()
    return [_user_summary(db, u) for u in users]


@router.get("/pending-billing")
def admin_pending_billing(
    status: Optional[str] = "pending",
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Lista compras pendentes/claimed/canceled para acompanhamento."""
    q = db.query(PendingBillingAccount)
    if status:
        q = q.filter(PendingBillingAccount.status == status)
    items = q.order_by(PendingBillingAccount.created_at.desc()).limit(200).all()
    return [_pending_summary(p) for p in items]


@router.post("/pending-billing/{pending_id}/claim")
def admin_claim_pending_billing(
    pending_id: int,
    payload: PendingBillingClaimRequest = PendingBillingClaimRequest(),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Vincula compra pendente a usuário existente.

    Se user_id não for informado, tenta encontrar usuário pelo email comprador.
    """
    pending = db.query(PendingBillingAccount).filter(PendingBillingAccount.id == pending_id).first()
    if not pending:
        raise HTTPException(404, "Compra pendente não encontrada.")
    if pending.status != "pending":
        raise HTTPException(400, "Compra não está pendente.")

    user = None
    if payload.user_id:
        user = db.query(User).filter(User.id == payload.user_id).first()
    else:
        user = db.query(User).filter(User.email == pending.buyer_email).first()
    if not user:
        raise HTTPException(404, "Usuário para vincular não encontrado.")

    billing_service.claim_pending_for_user(db, user)
    db.commit()
    db.refresh(pending)
    return {"ok": True, "pending": _pending_summary(pending), "user": _user_summary(db, user)}


@router.post("/pending-billing/{pending_id}/ignore")
def admin_ignore_pending_billing(
    pending_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Marca compra pendente como ignorada."""
    pending = db.query(PendingBillingAccount).filter(PendingBillingAccount.id == pending_id).first()
    if not pending:
        raise HTTPException(404, "Compra pendente não encontrada.")
    pending.status = "ignored"
    db.commit()
    db.refresh(pending)
    return {"ok": True, "pending": _pending_summary(pending)}


@router.put("/users/{user_id}")
def admin_update_user(
    user_id: int,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Usuário não encontrado.")

    if payload.is_active is not None:
        # evita o admin logado se desativar sem querer
        if user.id == admin.id and payload.is_active is False:
            raise HTTPException(400, "Você não pode desativar sua própria conta admin.")
        user.is_active = payload.is_active
    if payload.is_admin is not None:
        if user.id == admin.id and payload.is_admin is False and (user.email or "").lower() not in _admin_email_set():
            raise HTTPException(400, "Você não pode remover seu próprio admin sem ADMIN_EMAILS.")
        user.is_admin = payload.is_admin
    if payload.plan is not None:
        user.plan = plan_limits.normalize_plan(payload.plan.strip() or user.plan)
        plan_limits.sync_ai_limit_for_user(db, user)
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return _user_summary(db, user)


@router.delete("/users/{user_id}", status_code=204)
def admin_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Exclui usuário e dados operacionais vinculados.

    Ação destrutiva. Mantém BillingWebhookEvent como auditoria (não possui FK para User).
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Usuário não encontrado.")
    if user.id == admin.id:
        raise HTTPException(400, "Você não pode excluir sua própria conta admin.")

    # IDs auxiliares
    flow_ids = [x[0] for x in db.query(Flow.id).filter(Flow.owner_id == user.id).all()]
    lead_ids = [x[0] for x in db.query(Lead.id).filter(Lead.owner_id == user.id).all()]
    conn_ids = [x[0] for x in db.query(WhatsAppConnection.id).filter(WhatsAppConnection.owner_id == user.id).all()]
    kb_ids = [x[0] for x in db.query(KnowledgeBase.id).filter(KnowledgeBase.owner_id == user.id).all()]

    # WhatsApp dependentes
    if conn_ids:
        db.query(WhatsAppInboundEvent).filter(WhatsAppInboundEvent.connection_id.in_(conn_ids)).delete(synchronize_session=False)
        db.query(WhatsAppOutboundMessage).filter(WhatsAppOutboundMessage.connection_id.in_(conn_ids)).delete(synchronize_session=False)
        db.query(WhatsAppContactState).filter(WhatsAppContactState.connection_id.in_(conn_ids)).delete(synchronize_session=False)
        db.query(WhatsAppConnection).filter(WhatsAppConnection.id.in_(conn_ids)).delete(synchronize_session=False)

    # Conversas/mensagens por fluxos do usuário
    if flow_ids:
        conv_ids = [x[0] for x in db.query(Conversation.id).filter(Conversation.flow_id.in_(flow_ids)).all()]
        if conv_ids:
            db.query(Message).filter(Message.conversation_id.in_(conv_ids)).delete(synchronize_session=False)
            db.query(Conversation).filter(Conversation.id.in_(conv_ids)).delete(synchronize_session=False)

    # Leads, notas, tarefas e campos personalizados vinculados
    if lead_ids:
        db.query(LeadNote).filter(LeadNote.lead_id.in_(lead_ids)).delete(synchronize_session=False)
        db.query(CrmTask).filter(CrmTask.lead_id.in_(lead_ids)).delete(synchronize_session=False)
        db.query(CustomFieldValue).filter(CustomFieldValue.lead_id.in_(lead_ids)).delete(synchronize_session=False)
        db.query(Appointment).filter(Appointment.lead_id.in_(lead_ids)).update({Appointment.lead_id: None}, synchronize_session=False)
        db.query(Lead).filter(Lead.id.in_(lead_ids)).delete(synchronize_session=False)

    # Fluxos
    if flow_ids:
        db.query(Flow).filter(Flow.id.in_(flow_ids)).delete(synchronize_session=False)

    # Agenda/IA/Calendar/ROI/Billing
    db.query(Appointment).filter(Appointment.owner_id == user.id).delete(synchronize_session=False)

    # IMPORTANTE: AISettings pode referenciar KnowledgeBase via knowledge_base_id.
    # Portanto removemos AISettings ANTES de apagar KnowledgeBase, evitando erro de FK.
    db.query(AISettings).filter(AISettings.owner_id == user.id).delete(synchronize_session=False)
    if kb_ids:
        db.query(KnowledgeChunk).filter(KnowledgeChunk.knowledge_base_id.in_(kb_ids)).delete(synchronize_session=False)
        db.query(KnowledgeBase).filter(KnowledgeBase.id.in_(kb_ids)).delete(synchronize_session=False)

    db.query(CalendarConnection).filter(CalendarConnection.owner_id == user.id).delete(synchronize_session=False)
    db.query(CustomFieldValue).filter(CustomFieldValue.owner_id == user.id).delete(synchronize_session=False)
    db.query(CustomField).filter(CustomField.owner_id == user.id).delete(synchronize_session=False)
    db.query(CrmPipelineStage).filter(CrmPipelineStage.owner_id == user.id).delete(synchronize_session=False)
    db.query(CrmPipeline).filter(CrmPipeline.owner_id == user.id).delete(synchronize_session=False)
    db.query(CrmTag).filter(CrmTag.owner_id == user.id).delete(synchronize_session=False)
    db.query(CrmTask).filter(CrmTask.owner_id == user.id).delete(synchronize_session=False)
    db.query(QuickReply).filter(QuickReply.owner_id == user.id).delete(synchronize_session=False)
    db.query(ROISettings).filter(ROISettings.owner_id == user.id).delete(synchronize_session=False)
    db.query(Subscription).filter(Subscription.owner_id == user.id).delete(synchronize_session=False)
    db.query(PendingBillingAccount).filter(
        (PendingBillingAccount.claimed_user_id == user.id) | (PendingBillingAccount.buyer_email == user.email)
    ).delete(synchronize_session=False)

    db.delete(user)
    db.commit()
    return
