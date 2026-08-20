"""
Configuração de banco de dados com SQLAlchemy.
Suporta SQLite (dev/testes) e PostgreSQL (produção) via variável DATABASE_URL.
"""
import logging
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base, Session

from .config import settings

logger = logging.getLogger("whatsflow.database")


def _create_engine():
    """Cria engine do SQLAlchemy com base na URL do banco."""
    url = settings.database_url
    if url.startswith("sqlite"):
        db_path = url.replace("sqlite:///", "").replace("sqlite://", "")
        if db_path and db_path != ":memory:":
            p = Path(db_path)
            if not p.is_absolute():
                p = Path.cwd() / p
            p.parent.mkdir(parents=True, exist_ok=True)
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=False,
        )
    # PostgreSQL - SQLAlchemy 2.0 usa psycopg v3 automaticamente para URLs postgresql+psycopg://
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url, pool_pre_ping=True, echo=False)


engine = _create_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Session:
    """Gerador de sessão do banco - dependency do FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Auto-migração leve (aditiva e idempotente).
#
# IMPORTANTE:
# - O projeto usa Base.metadata.create_all(), que cria tabelas novas, mas NÃO
#   adiciona colunas novas em tabelas já existentes.
# - Por isso, toda coluna nova em tabela existente entra aqui.
# - Cada coluna roda em sua PRÓPRIA transação. Em PostgreSQL, se um ALTER falha
#   dentro de uma transação compartilhada, a transação inteira fica abortada e
#   pode derrubar o startup com PendingRollbackError. Separar por coluna evita isso.
#
# Cada entrada: (tabela, coluna, definicao_sql, default_para_registros_existentes)
# --------------------------------------------------------------------------- #
_ADDITIVE_COLUMNS = [
    ("flows", "mode", "VARCHAR(20)", "guided"),
    ("users", "is_admin", "BOOLEAN", False),

    # WhatsAppConnection evoluiu em fases (Meta -> Evolution/QR).
    ("whatsapp_connections", "phone_number", "VARCHAR(40)", None),
    ("whatsapp_connections", "flow_id", "INTEGER", None),
    ("whatsapp_connections", "phone_number_id", "VARCHAR(100)", None),
    ("whatsapp_connections", "waba_id", "VARCHAR(100)", None),
    ("whatsapp_connections", "access_token_enc", "TEXT", None),
    ("whatsapp_connections", "access_token_last4", "VARCHAR(8)", None),
    ("whatsapp_connections", "last_error", "TEXT", None),
    ("whatsapp_connections", "evolution_instance_name", "VARCHAR(150)", None),
    ("whatsapp_connections", "evolution_api_key_enc", "TEXT", None),
    ("whatsapp_connections", "webhook_secret_enc", "TEXT", None),
    ("whatsapp_connections", "created_at", "TIMESTAMP", None),
    ("whatsapp_connections", "updated_at", "TIMESTAMP", None),
    ("whatsapp_connections", "automation_paused", "BOOLEAN", False),

    # CRM 1.0 — colunas aditivas em leads para separar origens e vincular conversa/conexao.
    ("leads", "conversation_id", "INTEGER", None),
    ("leads", "connection_id", "INTEGER", None),
    ("leads", "last_interaction_at", "TIMESTAMP", None),
    ("leads", "updated_at", "TIMESTAMP", None),
    ("leads", "tags", "JSON", None),
    ("leads", "deal_value", "FLOAT", None),
    ("leads", "converted_at", "TIMESTAMP", None),
    ("leads", "lost_reason", "TEXT", None),
    ("leads", "pipeline_type", "VARCHAR(50)", "generic"),
    ("leads", "pipeline_stage", "VARCHAR(100)", "novo"),

    # Agenda avançada / preparação Google Calendar (C.2)
    ("appointments", "appointment_type", "VARCHAR(50)", "generic"),
    ("appointments", "external_calendar_provider", "VARCHAR(50)", None),
    ("appointments", "external_event_id", "VARCHAR(255)", None),
    ("appointments", "calendar_sync_status", "VARCHAR(50)", "not_synced"),
    ("appointments", "calendar_last_error", "TEXT", None),
    ("appointments", "unit_name", "VARCHAR(120)", None),

    # Futuras colunas aditivas em tabelas existentes entram aqui.
    # Ex.: ("users", "is_admin", "BOOLEAN", "0"),
]


def _table_names() -> set[str]:
    try:
        return set(inspect(engine).get_table_names())
    except Exception as exc:
        logger.warning("Nao foi possivel inspecionar tabelas p/ auto-migracao: %s", exc)
        return set()


def _column_names(table: str) -> set[str]:
    try:
        return {c["name"] for c in inspect(engine).get_columns(table)}
    except Exception as exc:
        logger.warning("Nao foi possivel inspecionar colunas de %s: %s", table, exc)
        return set()


def _run_additive_migrations():
    """Adiciona colunas novas em tabelas existentes, de forma segura e idempotente."""
    existing_tables = _table_names()
    if not existing_tables:
        return

    for table, column, sql_type, default in _ADDITIVE_COLUMNS:
        if table not in existing_tables:
            continue  # tabela nova -> create_all ja cria com a coluna

        cols = _column_names(table)
        if column in cols:
            continue

        try:
            # Cada coluna em transação própria para evitar PendingRollbackError no Postgres.
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {sql_type}'))
                if default is not None:
                    conn.execute(
                        text(f'UPDATE {table} SET {column} = :d WHERE {column} IS NULL'),
                        {"d": default},
                    )
            logger.info("Auto-migracao: coluna %s.%s adicionada.", table, column)
        except Exception as exc:
            # Nunca deixa a auto-migracao derrubar o app.
            # Em corrida/deploy parcial, a coluna pode ter sido criada entre o inspect e o ALTER.
            logger.warning("Auto-migracao de %s.%s falhou (seguindo): %s", table, column, exc)


def _run_data_backfills():
    """Preenche dados nulos de colunas aditivas sem tocar em dados já existentes."""
    tables = _table_names()
    try:
        with engine.begin() as conn:
            if "whatsapp_connections" in tables:
                cols = _column_names("whatsapp_connections")
                if "created_at" in cols:
                    conn.execute(text("UPDATE whatsapp_connections SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
                if "updated_at" in cols:
                    conn.execute(text("UPDATE whatsapp_connections SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL"))

            if "leads" in tables:
                cols = _column_names("leads")
                if "updated_at" in cols:
                    conn.execute(text("UPDATE leads SET updated_at = created_at WHERE updated_at IS NULL AND created_at IS NOT NULL"))
                if "last_interaction_at" in cols:
                    conn.execute(text("UPDATE leads SET last_interaction_at = created_at WHERE last_interaction_at IS NULL AND created_at IS NOT NULL"))
    except Exception as exc:
        logger.warning("Backfill de dados antigos falhou (seguindo): %s", exc)


def init_db():
    """Cria todas as tabelas no banco e aplica auto-migrações aditivas."""
    from . import models  # noqa: F401 - importar registra modelos
    Base.metadata.create_all(bind=engine)
    _run_additive_migrations()
    _run_data_backfills()
