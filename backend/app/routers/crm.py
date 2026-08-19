"""
EMG-1A — CRM operacional vertical.

Recursos de base para transformar Leads em Contatos & CRM:
- etiquetas gerenciáveis;
- campos personalizados;
- valores personalizados por lead;
- pipelines/etapas;
- tarefas;
- respostas rápidas;
- bootstrap inicial para operação Emagrecentro.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    CrmPipeline,
    CrmPipelineStage,
    CrmTag,
    CrmTask,
    CustomField,
    CustomFieldValue,
    Lead,
    QuickReply,
    User,
)

router = APIRouter()


# --------------------------------------------------------------------------- #
# Schemas locais: mantêm a fase isolada e aditiva.
# --------------------------------------------------------------------------- #
class TagIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: Optional[str] = Field("#3b82f6", max_length=20)
    description: Optional[str] = None
    is_active: Optional[bool] = True


class CustomFieldIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    key: Optional[str] = Field(None, max_length=120)
    field_type: str = Field("text", max_length=30)
    options: Optional[list[str]] = None
    required: bool = False
    show_in_table: bool = False
    sort_order: int = 0
    is_active: bool = True


class CustomValuesIn(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class PipelineIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None
    is_default: bool = False
    is_active: bool = True


class PipelineStageIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    slug: Optional[str] = Field(None, max_length=120)
    color: Optional[str] = Field("#3b82f6", max_length=20)
    sort_order: int = 0
    probability: int = 0
    is_won: bool = False
    is_lost: bool = False


class TaskIn(BaseModel):
    lead_id: Optional[int] = None
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    status: str = Field("pendente", max_length=50)
    task_type: str = Field("follow_up", max_length=50)
    due_at: Optional[datetime] = None
    assigned_to: Optional[str] = Field(None, max_length=255)
    priority: str = Field("normal", max_length=20)


class QuickReplyIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    content: str = Field(..., min_length=1)
    category: Optional[str] = Field(None, max_length=80)
    is_active: bool = True


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _slugify(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9áàâãéêíóôõúçñ]+", "_", value, flags=re.I)
    value = value.strip("_")
    return value or "campo"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _lead_or_404(db: Session, user: User, lead_id: int) -> Lead:
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == user.id).first()
    if not lead:
        raise HTTPException(404, "Contato/lead não encontrado.")
    return lead


def _tag_out(db: Session, tag: CrmTag) -> dict:
    count = 0
    leads = db.query(Lead).filter(Lead.owner_id == tag.owner_id).all()
    needle = (tag.name or "").strip().lower()
    for lead in leads:
        if any(str(t).strip().lower() == needle for t in (lead.tags or [])):
            count += 1
    return {
        "id": tag.id,
        "name": tag.name,
        "color": tag.color,
        "description": tag.description,
        "is_active": tag.is_active,
        "contacts_count": count,
        "created_at": tag.created_at.isoformat() if tag.created_at else None,
        "updated_at": tag.updated_at.isoformat() if tag.updated_at else None,
    }


def _field_out(field: CustomField) -> dict:
    return {
        "id": field.id,
        "name": field.name,
        "key": field.key,
        "field_type": field.field_type,
        "options": field.options or [],
        "required": field.required,
        "show_in_table": field.show_in_table,
        "sort_order": field.sort_order,
        "is_active": field.is_active,
        "created_at": field.created_at.isoformat() if field.created_at else None,
        "updated_at": field.updated_at.isoformat() if field.updated_at else None,
    }


def _pipeline_out(db: Session, pipeline: CrmPipeline) -> dict:
    stages = (
        db.query(CrmPipelineStage)
        .filter(CrmPipelineStage.pipeline_id == pipeline.id, CrmPipelineStage.owner_id == pipeline.owner_id)
        .order_by(CrmPipelineStage.sort_order.asc(), CrmPipelineStage.id.asc())
        .all()
    )
    return {
        "id": pipeline.id,
        "name": pipeline.name,
        "description": pipeline.description,
        "is_default": pipeline.is_default,
        "is_active": pipeline.is_active,
        "stages": [_stage_out(s) for s in stages],
        "created_at": pipeline.created_at.isoformat() if pipeline.created_at else None,
        "updated_at": pipeline.updated_at.isoformat() if pipeline.updated_at else None,
    }


def _stage_out(stage: CrmPipelineStage) -> dict:
    return {
        "id": stage.id,
        "pipeline_id": stage.pipeline_id,
        "name": stage.name,
        "slug": stage.slug,
        "color": stage.color,
        "sort_order": stage.sort_order,
        "probability": stage.probability,
        "is_won": stage.is_won,
        "is_lost": stage.is_lost,
        "created_at": stage.created_at.isoformat() if stage.created_at else None,
        "updated_at": stage.updated_at.isoformat() if stage.updated_at else None,
    }


def _task_out(db: Session, task: CrmTask) -> dict:
    lead = db.query(Lead).filter(Lead.id == task.lead_id, Lead.owner_id == task.owner_id).first() if task.lead_id else None
    return {
        "id": task.id,
        "lead_id": task.lead_id,
        "lead_name": lead.name if lead else None,
        "lead_phone": lead.phone if lead else None,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "task_type": task.task_type,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "assigned_to": task.assigned_to,
        "priority": task.priority,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def _quick_reply_out(q: QuickReply) -> dict:
    return {
        "id": q.id,
        "title": q.title,
        "content": q.content,
        "category": q.category,
        "is_active": q.is_active,
        "created_at": q.created_at.isoformat() if q.created_at else None,
        "updated_at": q.updated_at.isoformat() if q.updated_at else None,
    }


# --------------------------------------------------------------------------- #
# Bootstrap Emagrecentro
# --------------------------------------------------------------------------- #
@router.post("/bootstrap/emagrecentro")
def bootstrap_emagrecentro(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cria base inicial de CRM vertical para uma unidade Emagrecentro.

    Idempotente: não duplica itens com mesmo nome/chave.
    """
    created = {"tags": 0, "fields": 0, "pipelines": 0, "stages": 0, "quick_replies": 0}

    default_tags = [
        ("Lead", "#3b82f6"), ("Agendou", "#22c55e"), ("Compareceu", "#14b8a6"),
        ("Não compareceu", "#ef4444"), ("Comprou", "#10b981"), ("Não comprou", "#f97316"),
        ("Emagrecimento", "#eab308"), ("Gordura localizada", "#f59e0b"), ("Flacidez", "#facc15"),
        ("Indicação", "#a16207"), ("Desqualificado", "#ef4444"),
    ]
    existing_tags = {t.name.strip().lower() for t in db.query(CrmTag).filter(CrmTag.owner_id == current_user.id).all()}
    for name, color in default_tags:
        if name.lower() not in existing_tags:
            db.add(CrmTag(owner_id=current_user.id, name=name, color=color))
            created["tags"] += 1

    default_fields = [
        ("Unidade de interesse", "unidade_interesse", "text", True),
        ("Procedimento de interesse", "procedimento_interesse", "text", True),
        ("Condição de saúde", "condicao_saude", "textarea", False),
        ("Link do anúncio", "link_anuncio", "text", False),
        ("Data da avaliação", "data_avaliacao", "date", True),
        ("Horário da avaliação", "horario_avaliacao", "text", True),
        ("Gordura local - área", "gordura_local_area", "text", False),
        ("Emagrecimento - kg", "emagrecimento_kg", "number", False),
        ("Origem da campanha", "origem_campanha", "text", True),
    ]
    existing_fields = {f.key for f in db.query(CustomField).filter(CustomField.owner_id == current_user.id).all()}
    for idx, (name, key, field_type, show) in enumerate(default_fields, start=1):
        if key not in existing_fields:
            db.add(CustomField(
                owner_id=current_user.id, name=name, key=key, field_type=field_type,
                show_in_table=show, sort_order=idx,
            ))
            created["fields"] += 1

    pipeline = db.query(CrmPipeline).filter(CrmPipeline.owner_id == current_user.id, CrmPipeline.name == "Funil Emagrecentro").first()
    if not pipeline:
        pipeline = CrmPipeline(owner_id=current_user.id, name="Funil Emagrecentro", description="Funil padrão para avaliação, comparecimento e compra.", is_default=True)
        db.add(pipeline)
        db.flush()
        created["pipelines"] += 1
    stages = [
        ("Lead novo", "lead_novo", "#3b82f6", 1, 5, False, False),
        ("Em conversa", "em_conversa", "#6366f1", 2, 15, False, False),
        ("Agendou avaliação", "agendou_avaliacao", "#22c55e", 3, 35, False, False),
        ("Compareceu", "compareceu", "#14b8a6", 4, 55, False, False),
        ("Não compareceu", "nao_compareceu", "#ef4444", 5, 20, False, True),
        ("Comprou", "comprou", "#10b981", 6, 100, True, False),
        ("Não comprou", "nao_comprou", "#f97316", 7, 0, False, True),
        ("Reativação", "reativacao", "#a855f7", 8, 10, False, False),
    ]
    existing_stages = {s.slug for s in db.query(CrmPipelineStage).filter(CrmPipelineStage.owner_id == current_user.id, CrmPipelineStage.pipeline_id == pipeline.id).all()}
    for name, slug, color, order, prob, is_won, is_lost in stages:
        if slug not in existing_stages:
            db.add(CrmPipelineStage(
                owner_id=current_user.id, pipeline_id=pipeline.id, name=name, slug=slug,
                color=color, sort_order=order, probability=prob, is_won=is_won, is_lost=is_lost,
            ))
            created["stages"] += 1

    quick_replies = [
        ("Saudação", "Olá, {{primeiro_nome}}! Tudo bem? Sou da Emagrecentro e posso te ajudar a agendar sua avaliação.", "Atendimento"),
        ("Confirmar avaliação", "{{primeiro_nome}}, sua avaliação está agendada para {{data}} às {{hora}}. Posso confirmar sua presença?", "Agenda"),
        ("Reagendar falta", "Oi, {{primeiro_nome}}! Vi que não conseguimos te atender no horário combinado. Quer que eu veja um novo horário para sua avaliação?", "Reativação"),
        ("Condição de pagamento", "Os protocolos podem ser parcelados. A condição exata é apresentada na avaliação, após entendermos seu objetivo e o melhor protocolo.", "Comercial"),
    ]
    existing_qr = {q.title.strip().lower() for q in db.query(QuickReply).filter(QuickReply.owner_id == current_user.id).all()}
    for title, content, category in quick_replies:
        if title.lower() not in existing_qr:
            db.add(QuickReply(owner_id=current_user.id, title=title, content=content, category=category))
            created["quick_replies"] += 1

    db.commit()
    return {"ok": True, "created": created}


# --------------------------------------------------------------------------- #
# Etiquetas
# --------------------------------------------------------------------------- #
@router.get("/tags")
def list_tags(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tags = db.query(CrmTag).filter(CrmTag.owner_id == current_user.id).order_by(CrmTag.name.asc()).all()
    return [_tag_out(db, t) for t in tags]


@router.post("/tags", status_code=201)
def create_tag(payload: TagIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tag = CrmTag(owner_id=current_user.id, **payload.model_dump())
    db.add(tag)
    db.commit(); db.refresh(tag)
    return _tag_out(db, tag)


@router.put("/tags/{tag_id}")
def update_tag(tag_id: int, payload: TagIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tag = db.query(CrmTag).filter(CrmTag.id == tag_id, CrmTag.owner_id == current_user.id).first()
    if not tag:
        raise HTTPException(404, "Etiqueta não encontrada.")
    for k, v in payload.model_dump().items():
        setattr(tag, k, v)
    tag.updated_at = _now()
    db.commit(); db.refresh(tag)
    return _tag_out(db, tag)


@router.delete("/tags/{tag_id}", status_code=204)
def delete_tag(tag_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tag = db.query(CrmTag).filter(CrmTag.id == tag_id, CrmTag.owner_id == current_user.id).first()
    if not tag:
        raise HTTPException(404, "Etiqueta não encontrada.")
    db.delete(tag); db.commit(); return


# --------------------------------------------------------------------------- #
# Campos personalizados
# --------------------------------------------------------------------------- #
@router.get("/custom-fields")
def list_custom_fields(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = db.query(CustomField).filter(CustomField.owner_id == current_user.id).order_by(CustomField.sort_order.asc(), CustomField.name.asc()).all()
    return [_field_out(f) for f in items]


@router.post("/custom-fields", status_code=201)
def create_custom_field(payload: CustomFieldIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    data = payload.model_dump()
    data["key"] = _slugify(data.get("key") or data["name"])
    field = CustomField(owner_id=current_user.id, **data)
    db.add(field); db.commit(); db.refresh(field)
    return _field_out(field)


@router.put("/custom-fields/{field_id}")
def update_custom_field(field_id: int, payload: CustomFieldIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    field = db.query(CustomField).filter(CustomField.id == field_id, CustomField.owner_id == current_user.id).first()
    if not field:
        raise HTTPException(404, "Campo personalizado não encontrado.")
    data = payload.model_dump()
    data["key"] = _slugify(data.get("key") or data["name"])
    for k, v in data.items():
        setattr(field, k, v)
    field.updated_at = _now()
    db.commit(); db.refresh(field)
    return _field_out(field)


@router.delete("/custom-fields/{field_id}", status_code=204)
def delete_custom_field(field_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    field = db.query(CustomField).filter(CustomField.id == field_id, CustomField.owner_id == current_user.id).first()
    if not field:
        raise HTTPException(404, "Campo personalizado não encontrado.")
    db.query(CustomFieldValue).filter(CustomFieldValue.field_id == field.id, CustomFieldValue.owner_id == current_user.id).delete(synchronize_session=False)
    db.delete(field); db.commit(); return


@router.get("/contact-field-values")
def contact_field_values(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Valores de campos marcados para aparecer na tabela de contatos."""
    fields = db.query(CustomField).filter(
        CustomField.owner_id == current_user.id,
        CustomField.is_active == True,  # noqa: E712
        CustomField.show_in_table == True,  # noqa: E712
    ).all()
    field_ids = [f.id for f in fields]
    field_by_id = {f.id: f for f in fields}
    result: dict[str, dict[str, str]] = {}
    if not field_ids:
        return result
    values = db.query(CustomFieldValue).filter(
        CustomFieldValue.owner_id == current_user.id,
        CustomFieldValue.field_id.in_(field_ids),
    ).all()
    for v in values:
        f = field_by_id.get(v.field_id)
        if not f:
            continue
        result.setdefault(str(v.lead_id), {})[f.key] = v.value
    return result


@router.get("/leads/{lead_id}/custom-values")
def get_lead_custom_values(lead_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _lead_or_404(db, current_user, lead_id)
    fields = db.query(CustomField).filter(CustomField.owner_id == current_user.id, CustomField.is_active == True).all()  # noqa: E712
    values = db.query(CustomFieldValue).filter(CustomFieldValue.owner_id == current_user.id, CustomFieldValue.lead_id == lead_id).all()
    by_field = {v.field_id: v.value for v in values}
    return [{**_field_out(f), "value": by_field.get(f.id)} for f in fields]


@router.put("/leads/{lead_id}/custom-values")
def set_lead_custom_values(lead_id: int, payload: CustomValuesIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _lead_or_404(db, current_user, lead_id)
    fields = db.query(CustomField).filter(CustomField.owner_id == current_user.id).all()
    by_key = {f.key: f for f in fields}
    by_id = {str(f.id): f for f in fields}
    saved = 0
    for raw_key, raw_value in payload.values.items():
        field = by_key.get(str(raw_key)) or by_id.get(str(raw_key))
        if not field:
            continue
        val = "" if raw_value is None else str(raw_value)
        existing = db.query(CustomFieldValue).filter(
            CustomFieldValue.owner_id == current_user.id,
            CustomFieldValue.lead_id == lead_id,
            CustomFieldValue.field_id == field.id,
        ).first()
        if not existing:
            existing = CustomFieldValue(owner_id=current_user.id, lead_id=lead_id, field_id=field.id)
            db.add(existing)
        existing.value = val
        existing.updated_at = _now()
        saved += 1
    db.commit()
    return {"ok": True, "saved": saved}


# --------------------------------------------------------------------------- #
# Pipelines e etapas
# --------------------------------------------------------------------------- #
@router.get("/pipelines")
def list_pipelines(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = db.query(CrmPipeline).filter(CrmPipeline.owner_id == current_user.id).order_by(CrmPipeline.created_at.desc()).all()
    return [_pipeline_out(db, p) for p in items]


@router.post("/pipelines", status_code=201)
def create_pipeline(payload: PipelineIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if payload.is_default:
        db.query(CrmPipeline).filter(CrmPipeline.owner_id == current_user.id).update({CrmPipeline.is_default: False}, synchronize_session=False)
    p = CrmPipeline(owner_id=current_user.id, **payload.model_dump())
    db.add(p); db.commit(); db.refresh(p)
    return _pipeline_out(db, p)


@router.put("/pipelines/{pipeline_id}")
def update_pipeline(pipeline_id: int, payload: PipelineIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = db.query(CrmPipeline).filter(CrmPipeline.id == pipeline_id, CrmPipeline.owner_id == current_user.id).first()
    if not p:
        raise HTTPException(404, "Pipeline não encontrado.")
    if payload.is_default:
        db.query(CrmPipeline).filter(CrmPipeline.owner_id == current_user.id, CrmPipeline.id != p.id).update({CrmPipeline.is_default: False}, synchronize_session=False)
    for k, v in payload.model_dump().items():
        setattr(p, k, v)
    p.updated_at = _now()
    db.commit(); db.refresh(p)
    return _pipeline_out(db, p)


@router.delete("/pipelines/{pipeline_id}", status_code=204)
def delete_pipeline(pipeline_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = db.query(CrmPipeline).filter(CrmPipeline.id == pipeline_id, CrmPipeline.owner_id == current_user.id).first()
    if not p:
        raise HTTPException(404, "Pipeline não encontrado.")
    db.delete(p); db.commit(); return


@router.post("/pipelines/{pipeline_id}/stages", status_code=201)
def create_stage(pipeline_id: int, payload: PipelineStageIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = db.query(CrmPipeline).filter(CrmPipeline.id == pipeline_id, CrmPipeline.owner_id == current_user.id).first()
    if not p:
        raise HTTPException(404, "Pipeline não encontrado.")
    data = payload.model_dump(); data["slug"] = _slugify(data.get("slug") or data["name"])
    s = CrmPipelineStage(owner_id=current_user.id, pipeline_id=p.id, **data)
    db.add(s); db.commit(); db.refresh(s)
    return _stage_out(s)


@router.put("/pipeline-stages/{stage_id}")
def update_stage(stage_id: int, payload: PipelineStageIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    s = db.query(CrmPipelineStage).filter(CrmPipelineStage.id == stage_id, CrmPipelineStage.owner_id == current_user.id).first()
    if not s:
        raise HTTPException(404, "Etapa não encontrada.")
    data = payload.model_dump(); data["slug"] = _slugify(data.get("slug") or data["name"])
    for k, v in data.items():
        setattr(s, k, v)
    s.updated_at = _now()
    db.commit(); db.refresh(s)
    return _stage_out(s)


@router.delete("/pipeline-stages/{stage_id}", status_code=204)
def delete_stage(stage_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    s = db.query(CrmPipelineStage).filter(CrmPipelineStage.id == stage_id, CrmPipelineStage.owner_id == current_user.id).first()
    if not s:
        raise HTTPException(404, "Etapa não encontrada.")
    db.delete(s); db.commit(); return


# --------------------------------------------------------------------------- #
# Tarefas
# --------------------------------------------------------------------------- #
@router.get("/tasks")
def list_tasks(status: Optional[str] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(CrmTask).filter(CrmTask.owner_id == current_user.id)
    if status:
        q = q.filter(CrmTask.status == status)
    items = q.order_by(CrmTask.due_at.asc().nullslast(), CrmTask.created_at.desc()).limit(500).all()
    return [_task_out(db, t) for t in items]


@router.post("/tasks", status_code=201)
def create_task(payload: TaskIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if payload.lead_id:
        _lead_or_404(db, current_user, payload.lead_id)
    t = CrmTask(owner_id=current_user.id, **payload.model_dump())
    if t.status == "concluida" and not t.completed_at:
        t.completed_at = _now()
    db.add(t); db.commit(); db.refresh(t)
    return _task_out(db, t)


@router.put("/tasks/{task_id}")
def update_task(task_id: int, payload: TaskIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    t = db.query(CrmTask).filter(CrmTask.id == task_id, CrmTask.owner_id == current_user.id).first()
    if not t:
        raise HTTPException(404, "Tarefa não encontrada.")
    if payload.lead_id:
        _lead_or_404(db, current_user, payload.lead_id)
    old_status = t.status
    for k, v in payload.model_dump().items():
        setattr(t, k, v)
    if t.status == "concluida" and old_status != "concluida":
        t.completed_at = _now()
    elif t.status != "concluida":
        t.completed_at = None
    t.updated_at = _now()
    db.commit(); db.refresh(t)
    return _task_out(db, t)


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    t = db.query(CrmTask).filter(CrmTask.id == task_id, CrmTask.owner_id == current_user.id).first()
    if not t:
        raise HTTPException(404, "Tarefa não encontrada.")
    db.delete(t); db.commit(); return


# --------------------------------------------------------------------------- #
# Respostas rápidas
# --------------------------------------------------------------------------- #
@router.get("/quick-replies")
def list_quick_replies(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = db.query(QuickReply).filter(QuickReply.owner_id == current_user.id).order_by(QuickReply.category.asc().nullslast(), QuickReply.title.asc()).all()
    return [_quick_reply_out(q) for q in items]


@router.post("/quick-replies", status_code=201)
def create_quick_reply(payload: QuickReplyIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = QuickReply(owner_id=current_user.id, **payload.model_dump())
    db.add(q); db.commit(); db.refresh(q)
    return _quick_reply_out(q)


@router.put("/quick-replies/{reply_id}")
def update_quick_reply(reply_id: int, payload: QuickReplyIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(QuickReply).filter(QuickReply.id == reply_id, QuickReply.owner_id == current_user.id).first()
    if not q:
        raise HTTPException(404, "Resposta rápida não encontrada.")
    for k, v in payload.model_dump().items():
        setattr(q, k, v)
    q.updated_at = _now()
    db.commit(); db.refresh(q)
    return _quick_reply_out(q)


@router.delete("/quick-replies/{reply_id}", status_code=204)
def delete_quick_reply(reply_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(QuickReply).filter(QuickReply.id == reply_id, QuickReply.owner_id == current_user.id).first()
    if not q:
        raise HTTPException(404, "Resposta rápida não encontrada.")
    db.delete(q); db.commit(); return
