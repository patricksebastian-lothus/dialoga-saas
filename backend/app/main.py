"""
Ponto de entrada da aplicação FastAPI - dIAloga+ SaaS.
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .config import settings
from .database import init_db, SessionLocal
from .services.template_loader import seed_templates
from .routers import auth, templates, flows, leads, whatsapp, dashboard, inbox, appointments, calendar, setup, admin, billing, plans, crm
from .routers.whatsapp_meta import meta_webhook_router  # NOVO: webhook Meta (modo shadow)
from .routers.whatsapp_connections import router as whatsapp_connections_router  # NOVO: Fase 3
from .routers.ai import router as ai_router  # NOVO: Fase A (IA + RAG)
from .routers.whatsapp_evolution import evo_webhook_router  # NOVO: Fase 5 (Evolution/QR)
from .json import CustomJSONResponse

# Logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("whatsflow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Executa ao iniciar e ao encerrar a aplicação."""
    logger.info("Iniciando dIAloga+ SaaS...")
    init_db()
    # Popula templates JSON no banco caso estejam vazios
    db = SessionLocal()
    try:
        seed_templates(db)
    finally:
        db.close()
    logger.info("dIAloga+ pronto. Ambiente: %s", settings.app_env)
    yield
    logger.info("Encerrando dIAloga+...")


app = FastAPI(
    title="dIAloga+ SaaS",
    description="Plataforma de construção de chatbots de WhatsApp com templates prontos.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    default_response_class=CustomJSONResponse,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    """Endpoint raiz - status da API."""
    return {
        "app": "dIAloga+ SaaS",
        "version": "1.0.0",
        "status": "online",
        "env": settings.app_env,
        "docs": "/docs",
    }


@app.get("/health")
def health():
    """Health check para Render e monitoramento."""
    return {"status": "healthy"}


# Inclui routers da API
app.include_router(auth.router, prefix="/api/auth", tags=["Autenticação"])
app.include_router(templates.router, prefix="/api/templates", tags=["Templates"])
app.include_router(flows.router, prefix="/api/flows", tags=["Fluxos"])
app.include_router(leads.router, prefix="/api/leads", tags=["Leads"])
app.include_router(inbox.router, prefix="/api/inbox", tags=["Inbox Humano"])
app.include_router(appointments.router, prefix="/api/appointments", tags=["Agenda"])
app.include_router(calendar.router, prefix="/api/calendar", tags=["Calendario"])
app.include_router(setup.router, prefix="/api/setup", tags=["Setup"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(billing.router, prefix="/api/billing", tags=["Billing"])
app.include_router(plans.router, prefix="/api/plans", tags=["Planos"])
app.include_router(crm.router, prefix="/api/crm", tags=["CRM vertical"])
app.include_router(whatsapp.router, prefix="/api/whatsapp", tags=["WhatsApp"])
app.include_router(whatsapp_connections_router, prefix="/api/whatsapp/connections", tags=["WhatsApp Conexões"])  # NOVO: Fase 3
app.include_router(ai_router, prefix="/api/ai", tags=["IA"])  # NOVO: Fase A (IA + RAG)
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(whatsapp.webhook_router, tags=["Webhook"])          # legado (intacto): /webhook/whatsapp
app.include_router(meta_webhook_router, tags=["Webhook"])              # NOVO: /webhook/whatsapp/meta
app.include_router(evo_webhook_router, tags=["Webhook"])               # NOVO: /webhook/whatsapp/evo (Evolution/QR)
