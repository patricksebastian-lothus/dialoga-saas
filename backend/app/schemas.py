"""
Schemas Pydantic para validação de entrada/saída da API.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, EmailStr, Field


# =================== AUTH ===================
class UserCreate(BaseModel):
    """Dados para cadastro de usuário."""
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    company_name: str = Field(..., min_length=2, max_length=255)
    full_name: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)


class UserLogin(BaseModel):
    """Dados para login."""
    email: EmailStr
    password: str


class UserOut(BaseModel):
    """Dados públicos do usuário."""
    id: int
    email: EmailStr
    company_name: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    plan: str = "basico"
    is_admin: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    """Resposta de autenticação."""
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class PasswordResetRequest(BaseModel):
    """Solicitação de recuperação de senha."""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Confirmação de nova senha (simulado)."""
    email: EmailStr
    new_password: str = Field(..., min_length=6)


# =================== TEMPLATE ===================
class TemplateSummary(BaseModel):
    """Resumo de um template (listagem)."""
    slug: str
    name: str
    description: str
    category: str
    icon: str
    node_count: int = 0

    class Config:
        from_attributes = True


class TemplateDetail(BaseModel):
    """Detalhes completos de um template."""
    slug: str
    name: str
    description: str
    category: str
    icon: str
    flow_data: Dict[str, Any]


# =================== FLOW ===================
class FlowNode(BaseModel):
    """Estrutura de um nó do fluxo."""
    id: str
    # 'ai' e' o novo tipo (Fase A.2): responde com IA/RAG
    type: Literal["message", "question", "input", "condition", "delay", "webhook", "human", "end", "ai"]
    content: str = ""
    options: Optional[List[Dict[str, str]]] = None  # [{"label": "x", "value": "y", "next": "node_id"}]
    next: Optional[str] = None
    variable: Optional[str] = None  # nome da variável a capturar (para input/question)
    delay_seconds: Optional[int] = None
    condition: Optional[Dict[str, Any]] = None
    fallback: Optional[str] = None
    # Campo do nó 'ai': qual base de conhecimento usar (opcional; usa a padrao das AISettings se vazio)
    knowledge_base_id: Optional[int] = None
    # Campos para canvas visual
    position_x: Optional[float] = None  # posição X no canvas (pixels)
    position_y: Optional[float] = None  # posição Y no canvas (pixels)


class FlowCreate(BaseModel):
    """Criação de fluxo."""
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    nodes: List[FlowNode] = []
    start_node_id: Optional[str] = None
    template_slug: Optional[str] = None
    mode: Optional[Literal["guided", "ai_agent"]] = "guided"


class FlowUpdate(BaseModel):
    """Atualização de fluxo."""
    name: Optional[str] = None
    description: Optional[str] = None
    nodes: Optional[List[FlowNode]] = None
    start_node_id: Optional[str] = None
    active: Optional[bool] = None
    mode: Optional[Literal["guided", "ai_agent"]] = None


class FlowOut(BaseModel):
    """Fluxo retornado pela API."""
    id: int
    name: str
    description: Optional[str]
    nodes: List[Dict[str, Any]]
    start_node_id: Optional[str]
    active: bool
    template_slug: Optional[str]
    mode: str = "guided"
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# =================== LEAD ===================
class LeadOut(BaseModel):
    id: int
    flow_id: Optional[int]
    name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    stage: Optional[str]
    context: Optional[Dict[str, Any]]
    source: str
    status: str
    tags: Optional[List[str]] = None
    deal_value: Optional[float] = None
    converted_at: Optional[datetime] = None
    lost_reason: Optional[str] = None
    pipeline_type: Optional[str] = "generic"
    pipeline_stage: Optional[str] = "novo"
    conversation_id: Optional[int] = None
    connection_id: Optional[int] = None
    last_interaction_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LeadCreate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = "novo"
    stage: Optional[str] = None
    tags: Optional[List[str]] = None
    source: Optional[str] = "manual"
    pipeline_type: Optional[str] = "generic"
    pipeline_stage: Optional[str] = "novo"
    context: Optional[Dict[str, Any]] = None


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None
    stage: Optional[str] = None
    tags: Optional[List[str]] = None
    deal_value: Optional[float] = None
    lost_reason: Optional[str] = None
    pipeline_type: Optional[str] = None
    pipeline_stage: Optional[str] = None


class LeadNoteCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class LeadNoteOut(BaseModel):
    id: int
    lead_id: int
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


# =================== SIMULATOR ===================
class SimulatorStart(BaseModel):
    """Iniciar uma simulação (flow_id vem da URL)."""
    user_name: Optional[str] = "Visitante"
    user_phone: Optional[str] = None


class SimulatorMessage(BaseModel):
    """Enviar mensagem dentro da simulação."""
    conversation_id: int
    text: Optional[str] = None
    selected_option: Optional[str] = None


class SimulatorResponse(BaseModel):
    """Resposta do motor para o simulador."""
    conversation_id: int
    finished: bool = False
    current_node: Optional[Dict[str, Any]] = None
    bot_message: Optional[str] = None
    options: Optional[List[Dict[str, str]]] = None
    awaiting_input: bool = False
    context: Dict[str, Any] = {}
    messages: List[Dict[str, Any]] = []


# =================== APPOINTMENTS ===================
class AppointmentCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    scheduled_at: datetime
    lead_id: Optional[int] = None
    flow_id: Optional[int] = None
    status: Optional[Literal["solicitado", "confirmado", "cancelado", "realizado", "nao_compareceu"]] = "solicitado"
    appointment_type: Optional[str] = "generic"
    notes: Optional[str] = None


class AppointmentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    scheduled_at: Optional[datetime] = None
    lead_id: Optional[int] = None
    flow_id: Optional[int] = None
    status: Optional[Literal["solicitado", "confirmado", "cancelado", "realizado", "nao_compareceu"]] = None
    appointment_type: Optional[str] = None
    notes: Optional[str] = None
    unit_name: Optional[str] = None


class AppointmentOut(BaseModel):
    id: int
    owner_id: int
    lead_id: Optional[int] = None
    flow_id: Optional[int] = None
    title: str
    scheduled_at: datetime
    status: str
    appointment_type: Optional[str] = "generic"
    notes: Optional[str] = None
    unit_name: Optional[str] = None
    external_calendar_provider: Optional[str] = None
    external_event_id: Optional[str] = None
    calendar_sync_status: Optional[str] = "not_synced"
    calendar_last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    lead_name: Optional[str] = None
    lead_phone: Optional[str] = None
    flow_name: Optional[str] = None

    class Config:
        from_attributes = True


# =================== ROI SETTINGS ===================
class ROISettingsUpdate(BaseModel):
    average_ticket: float = Field(0, ge=0)
    currency: str = Field("BRL", max_length=10)


class ROISettingsOut(BaseModel):
    average_ticket: float = 0
    currency: str = "BRL"

    class Config:
        from_attributes = True


# =================== DASHBOARD ===================
class DashboardMetrics(BaseModel):
    flows_count: int
    active_flows_count: int
    leads_count: int
    leads_today: int
    leads_this_week: int
    conversations_total: int
    conversations_simulated: int
    conversations_real: int
    leads_by_day: List[Dict[str, Any]] = []
    recent_flows: List[Dict[str, Any]] = []
    recent_leads: List[Dict[str, Any]] = []


# =================== WHATSAPP ===================
class WhatsAppSendText(BaseModel):
    to: str = Field(..., description="Número com DDI, ex: 5511999999999")
    text: str
