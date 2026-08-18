"""
Modelos SQLAlchemy do WhatsFlow/dIAloga+.
Define entidades principais: User, Flow, Lead, LeadNote, Template, Conversation, Message.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, Text, DateTime, Boolean, ForeignKey, JSON, Float
)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.mutable import MutableDict, MutableList

from .database import Base


def utcnow():
    """Retorna datetime atual em UTC com timezone-aware."""
    return datetime.now(timezone.utc)


class User(Base):
    """Usuário do sistema (empresa)."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    plan = Column(String(50), default="basico")
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    flows = relationship("Flow", back_populates="owner", cascade="all, delete-orphan")
    leads = relationship("Lead", back_populates="owner", cascade="all, delete-orphan")
    whatsapp_connections = relationship(
        "WhatsAppConnection", back_populates="owner", cascade="all, delete-orphan"
    )


class Template(Base):
    """Template de chatbot disponível para importação."""
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(100), nullable=False)
    icon = Column(String(50), default="🤖")
    flow_data = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)


class Flow(Base):
    """Fluxo de chatbot criado por um usuário."""
    __tablename__ = "flows"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    nodes = Column(JSON, nullable=False, default=list)
    start_node_id = Column(String(100), nullable=True)
    active = Column(Boolean, default=True)
    template_slug = Column(String(100), nullable=True)
    mode = Column(String(20), default="guided", nullable=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    owner = relationship("User", back_populates="flows")
    leads = relationship("Lead", back_populates="flow")
    conversations = relationship(
        "Conversation", back_populates="flow", cascade="all, delete-orphan"
    )


class Lead(Base):
    """Lead capturado por um fluxo.

    CRM:
    - source diferencia simulator | whatsapp_evolution | whatsapp_meta | manual/import/api.
    - tags classificam operacionalmente o lead.
    - conversation_id/connection_id vinculam CRM à conversa e à conexão WhatsApp.
    """
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    flow_id = Column(Integer, ForeignKey("flows.id"), nullable=True)
    name = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True, index=True)
    email = Column(String(255), nullable=True)
    stage = Column(String(255), nullable=True)
    context = Column(MutableDict.as_mutable(JSON), nullable=True, default=dict)
    source = Column(String(50), default="simulator")
    status = Column(String(50), default="novo")
    tags = Column(MutableList.as_mutable(JSON), nullable=True, default=list)

    # Pipeline comercial simples (ROI real/manual)
    deal_value = Column(Float, nullable=True)          # valor real da venda quando convertido
    converted_at = Column(DateTime, nullable=True)    # quando virou convertido
    lost_reason = Column(Text, nullable=True)         # motivo quando perdido

    # Pipeline por nicho (C.2)
    pipeline_type = Column(String(50), default="generic", index=True)
    pipeline_stage = Column(String(100), default="novo", index=True)

    conversation_id = Column(Integer, nullable=True, index=True)
    connection_id = Column(Integer, nullable=True, index=True)
    last_interaction_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    owner = relationship("User", back_populates="leads")
    flow = relationship("Flow", back_populates="leads")


class LeadNote(Base):
    """Nota interna do CRM. Não é enviada ao WhatsApp."""
    __tablename__ = "lead_notes"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow, index=True)

    lead = relationship("Lead")


class ROISettings(Base):
    """Configuração simples de ROI por usuário/empresa.

    Fase Dashboard ROI básico: permite estimar receita potencial usando ticket médio.
    """
    __tablename__ = "roi_settings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    average_ticket = Column(Float, default=0.0)
    currency = Column(String(10), default="BRL")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    owner = relationship("User")


class CalendarConnection(Base):
    """Conexão OAuth com calendário externo (Google Calendar inicialmente)."""
    __tablename__ = "calendar_connections"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider = Column(String(50), default="google", nullable=False, index=True)
    status = Column(String(50), default="connected")
    calendar_id = Column(String(255), default="primary")
    access_token_enc = Column(Text, nullable=True)
    refresh_token_enc = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    owner = relationship("User")


class Appointment(Base):
    """Agendamento interno vinculado a lead/fluxo.

    Fase C.1: agenda interna sem Google Calendar.
    """
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True, index=True)
    flow_id = Column(Integer, ForeignKey("flows.id"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    scheduled_at = Column(DateTime, nullable=False, index=True)
    status = Column(String(50), default="solicitado", index=True)  # solicitado|confirmado|cancelado|realizado|nao_compareceu
    appointment_type = Column(String(50), default="generic", index=True)  # generic|avaliacao|consulta|banho_tosa|visita|test_drive|retorno|suporte
    notes = Column(Text, nullable=True)

    # Preparação para Google Calendar (C.2.3 futura)
    external_calendar_provider = Column(String(50), nullable=True)
    external_event_id = Column(String(255), nullable=True, index=True)
    calendar_sync_status = Column(String(50), default="not_synced")  # not_synced|synced|error|disabled
    calendar_last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    owner = relationship("User")
    lead = relationship("Lead")
    flow = relationship("Flow")


class Conversation(Base):
    """Histórico de uma conversa (real ou simulada)."""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    flow_id = Column(Integer, ForeignKey("flows.id"), nullable=False)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    user_phone = Column(String(50), nullable=True, index=True)
    channel = Column(String(50), default="simulator")
    state = Column(MutableDict.as_mutable(JSON), nullable=True, default=dict)
    is_active = Column(Boolean, default=True)
    started_at = Column(DateTime, default=utcnow)
    ended_at = Column(DateTime, nullable=True)

    flow = relationship("Flow", back_populates="conversations")
    messages = relationship(
        "Message", back_populates="conversation",
        cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(Base):
    """Mensagem individual dentro de uma conversa."""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    direction = Column(String(20), nullable=False)
    sender = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    node_id = Column(String(100), nullable=True)
    message_type = Column(String(50), default="text")
    created_at = Column(DateTime, default=utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class Subscription(Base):
    """Assinatura/acesso comercial do usuário no SaaS.

    Fase E.3: base para Hotmart/Eduzz e billing futuro.
    """
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider = Column(String(50), nullable=False, default="manual", index=True)
    external_id = Column(String(255), nullable=True, index=True)
    plan = Column(String(50), nullable=False, default="profissional")
    status = Column(String(50), nullable=False, default="active")  # active|inactive|canceled|refunded|overdue
    buyer_email = Column(String(255), nullable=True, index=True)
    product_name = Column(String(255), nullable=True)
    raw_payload = Column(JSON, nullable=True)
    started_at = Column(DateTime, nullable=True)
    canceled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    owner = relationship("User")


class PendingBillingAccount(Base):
    """Compra recebida antes do usuário se cadastrar.

    Quando o comprador se registra com o mesmo email, aplicamos o plano automaticamente.
    """
    __tablename__ = "pending_billing_accounts"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(50), nullable=False, index=True)
    external_id = Column(String(255), nullable=True, index=True)
    buyer_email = Column(String(255), nullable=False, index=True)
    plan = Column(String(50), nullable=False, default="profissional")
    status = Column(String(50), nullable=False, default="pending")  # pending|claimed|canceled|ignored
    product_name = Column(String(255), nullable=True)
    raw_payload = Column(JSON, nullable=True)
    claimed_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=utcnow, index=True)
    claimed_at = Column(DateTime, nullable=True)


class BillingWebhookEvent(Base):
    """Log de webhooks de billing para auditoria/idempotência."""
    __tablename__ = "billing_webhook_events"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(50), nullable=False, index=True)
    external_event_id = Column(String(255), nullable=False, index=True)
    event_type = Column(String(100), nullable=True)
    buyer_email = Column(String(255), nullable=True, index=True)
    raw_payload = Column(JSON, nullable=False)
    status = Column(String(50), default="received")  # received|processed|ignored|failed
    error = Column(Text, nullable=True)
    received_at = Column(DateTime, default=utcnow, index=True)
    processed_at = Column(DateTime, nullable=True)


# --- WhatsApp real + billing (tabelas NOVAS, aditivas) ---
from .models_whatsapp import (  # noqa: E402,F401
    WhatsAppConnection,
    WhatsAppInboundEvent,
    WhatsAppOutboundMessage,
    WhatsAppContactState,
)

# --- IA + RAG (Fase A) — tabelas NOVAS, aditivas ---
from .models_rag import (  # noqa: E402,F401
    KnowledgeBase,
    KnowledgeChunk,
    AISettings,
)


# --------------------------------------------------------------------------- #
# EMG-1A — CRM operacional vertical (Emagrecentro / clínicas)
# Tabelas novas e aditivas: create_all cria automaticamente sem migration manual.
# --------------------------------------------------------------------------- #
class CrmTag(Base):
    """Etiqueta gerenciável do CRM por tenant."""
    __tablename__ = "crm_tags"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False, index=True)
    color = Column(String(20), default="#3b82f6")
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    owner = relationship("User")


class CustomField(Base):
    """Campo personalizado que aparece na ficha do contato/lead."""
    __tablename__ = "custom_fields"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    key = Column(String(120), nullable=False, index=True)
    field_type = Column(String(30), default="text", nullable=False)  # text|number|date|select|boolean|textarea
    options = Column(MutableList.as_mutable(JSON), nullable=True, default=list)
    required = Column(Boolean, default=False, nullable=False)
    show_in_table = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    owner = relationship("User")


class CustomFieldValue(Base):
    """Valor de um campo personalizado para um lead/contato."""
    __tablename__ = "custom_field_values"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    field_id = Column(Integer, ForeignKey("custom_fields.id"), nullable=False, index=True)
    value = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    owner = relationship("User")
    lead = relationship("Lead")
    field = relationship("CustomField")


class CrmPipeline(Base):
    """Funil comercial/operacional por tenant."""
    __tablename__ = "crm_pipelines"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    owner = relationship("User")
    stages = relationship("CrmPipelineStage", back_populates="pipeline", cascade="all, delete-orphan")


class CrmPipelineStage(Base):
    """Etapa de um funil do CRM."""
    __tablename__ = "crm_pipeline_stages"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    pipeline_id = Column(Integer, ForeignKey("crm_pipelines.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    slug = Column(String(120), nullable=False, index=True)
    color = Column(String(20), default="#3b82f6")
    sort_order = Column(Integer, default=0, nullable=False)
    probability = Column(Integer, default=0, nullable=False)
    is_won = Column(Boolean, default=False, nullable=False)
    is_lost = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    owner = relationship("User")
    pipeline = relationship("CrmPipeline", back_populates="stages")


class CrmTask(Base):
    """Tarefa operacional ligada ou não a um lead."""
    __tablename__ = "crm_tasks"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="pendente", index=True)  # sem_status|pendente|em_andamento|aguardando_resposta|concluida
    task_type = Column(String(50), default="follow_up", index=True)
    due_at = Column(DateTime, nullable=True, index=True)
    assigned_to = Column(String(255), nullable=True)
    priority = Column(String(20), default="normal", index=True)  # baixa|normal|alta|urgente
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    completed_at = Column(DateTime, nullable=True)

    owner = relationship("User")
    lead = relationship("Lead")


class QuickReply(Base):
    """Resposta rápida para atendimento humano/Inbox."""
    __tablename__ = "quick_replies"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(120), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(80), nullable=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    owner = relationship("User")
