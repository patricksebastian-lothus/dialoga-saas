from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    debug: bool = True
    # Emails com acesso ao Painel Admin (separados por virgula).
    # Ex.: ADMIN_EMAILS=admin@seudominio.com.br,voce@gmail.com
    admin_emails: str = ""
    secret_key: str = "chave-padrao-desenvolvimento-troque-em-producao-64-caracteres-min"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 43200
    database_url: str = "sqlite:///./data/dialoga.db"
    cors_origins: str = "http://localhost:3000,http://localhost:8000,http://localhost:5500,http://127.0.0.1:5500,http://127.0.0.1:8000"
    host: str = "0.0.0.0"
    port: int = 8000

    whatsapp_api_url: str = "https://graph.facebook.com/v18.0"
    whatsapp_token: str = ""
    whatsapp_phone_id: str = ""
    whatsapp_verify_token: str = "dialoga-verify"

    max_upload_mb: int = 10
    rate_limit_per_minute: int = 60

    # =========================================================
    # NOVO — WhatsApp real + planos (Fase 0+). Todos com default seguro.
    # Como model_config tem extra="ignore" e todos tem default, o app sobe
    # sem nenhuma env nova; com as flags em False, o comportamento e' inerte.
    # =========================================================

    # --- Meta Cloud API ---
    whatsapp_meta_enabled: bool = False          # feature flag: OFF em producao ate validar
    meta_app_secret: str = ""                    # App Secret p/ validar X-Hub-Signature-256
    meta_graph_version: str = "v23.0"            # versao do Graph p/ ENVIO (webhook independe disso)

    # --- Criptografia de tokens (Fernet) ---
    wa_fernet_keys: str = ""                     # 1+ chaves Fernet separadas por virgula

    # --- Fila assincrona (arq + Redis) ---
    redis_url: str = "redis://localhost:6379/0"
    worker_enabled: bool = False                 # flag p/ habilitar processamento de fila

    # --- Evolution API (QR) ---
    evolution_enabled: bool = False
    evolution_base_url: str = ""          # URL da Evolution (Railway)
    evolution_global_api_key: str = ""    # AUTHENTICATION_API_KEY da Evolution
    # URL publica DESTE backend (p/ a Evolution mandar webhook de volta)
    public_base_url: str = "https://dialoga-backend-r1zp.onrender.com"

    # --- Google Calendar (Agenda C.2.3) ---
    google_calendar_enabled: bool = False
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""  # default: PUBLIC_BASE_URL + /api/calendar/google/callback
    frontend_base_url: str = "https://dialoga-frontend-wird.onrender.com"
    privacy_policy_url: str = "https://dialoga-frontend-wird.onrender.com/privacidade.html"
    terms_url: str = "https://dialoga-frontend-wird.onrender.com/termos.html"

    # --- IA / Gemini (Fase A) ---
    gemini_api_key: str = ""                     # Google AI Studio API key
    gemini_chat_model: str = "gemini-2.0-flash"  # modelo de chat (rapido e barato)
    ai_enabled: bool = False                     # feature flag global da IA

    # --- Billing ---
    billing_enabled: bool = False
    billing_provider: str = "manual"             # manual | hotmart | eduzz | asaas | stripe
    billing_default_plan: str = "profissional"
    hotmart_webhook_token: str = ""
    eduzz_webhook_token: str = ""
    hotmart_essencial_url: str = ""
    hotmart_profissional_url: str = ""
    hotmart_performance_url: str = ""
    eduzz_essencial_url: str = ""
    eduzz_profissional_url: str = ""
    eduzz_performance_url: str = ""
    asaas_api_key: str = ""
    asaas_webhook_token: str = ""
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def cors_origins_list(self) -> List[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
