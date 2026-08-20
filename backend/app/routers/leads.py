"""
Rotas de leads - CRM 1.0.

Inclui filtros por origem para separar:
- simulator
- whatsapp_evolution
- whatsapp_meta
- manual/import/api no futuro
"""
import csv
import io
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Conversation, CustomFieldValue, Flow, Lead, LeadNote, User
from ..schemas import LeadCreate, LeadOut, LeadUpdate, LeadNoteCreate, LeadNoteOut


router = APIRouter()


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, "Datas devem estar em ISO 8601 (YYYY-MM-DD).")


@router.get("", response_model=list[LeadOut])
def list_leads(
    flow_id: Optional[int] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    tag: Optional[str] = None,
    include_simulator: bool = True,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista leads com filtros opcionais."""
    q = db.query(Lead).filter(Lead.owner_id == current_user.id)

    if flow_id:
        q = q.filter(Lead.flow_id == flow_id)
    if status:
        q = q.filter(Lead.status == status)
    if source:
        q = q.filter(Lead.source == source)
    elif include_simulator is False:
        q = q.filter(Lead.source != "simulator")

    dt_from = _parse_date(date_from)
    dt_to = _parse_date(date_to)
    if dt_from:
        q = q.filter(Lead.created_at >= dt_from)
    if dt_to:
        q = q.filter(Lead.created_at <= dt_to)

    leads = q.order_by(Lead.created_at.desc()).all()
    if tag:
        needle = tag.strip().lower()
        leads = [l for l in leads if any(str(t).strip().lower() == needle for t in (l.tags or []))]
    return [LeadOut.model_validate(l) for l in leads]


def _normalize_tags(values: Optional[list[str]]) -> list[str]:
    seen = set()
    tags = []
    for t in values or []:
        tag = str(t or "").strip()
        key = tag.lower()
        if tag and key not in seen:
            seen.add(key)
            tags.append(tag)
    return tags


@router.post("", response_model=LeadOut, status_code=201)
def create_lead(
    payload: LeadCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cria contato/lead manualmente no CRM."""
    if not (payload.name or payload.phone or payload.email):
        raise HTTPException(400, "Informe pelo menos nome, telefone ou email.")
    lead = Lead(
        owner_id=current_user.id,
        flow_id=None,
        name=(payload.name or "").strip() or None,
        phone=(payload.phone or "").strip() or None,
        email=(payload.email or "").strip() or None,
        status=payload.status or "novo",
        stage=payload.stage,
        source=payload.source or "manual",
        tags=_normalize_tags(payload.tags),
        pipeline_type=payload.pipeline_type or "generic",
        pipeline_stage=payload.pipeline_stage or "novo",
        context=payload.context or {},
        last_interaction_at=datetime.now(timezone.utc),
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return LeadOut.model_validate(lead)


@router.put("/{lead_id}", response_model=LeadOut)
def update_lead(
    lead_id: int,
    payload: LeadUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Atualiza dados do lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == current_user.id).first()
    if not lead:
        raise HTTPException(404, "Lead não encontrado")

    if payload.name is not None:
        lead.name = payload.name
    if payload.phone is not None:
        lead.phone = payload.phone
    if payload.email is not None:
        lead.email = payload.email
    if payload.status is not None:
        lead.status = payload.status
        if payload.status == "convertido" and not getattr(lead, "converted_at", None):
            lead.converted_at = datetime.now(timezone.utc)
    if payload.deal_value is not None:
        lead.deal_value = float(payload.deal_value)
        if lead.status == "convertido" and not getattr(lead, "converted_at", None):
            lead.converted_at = datetime.now(timezone.utc)
    if payload.lost_reason is not None:
        lead.lost_reason = payload.lost_reason
    if payload.pipeline_type is not None:
        lead.pipeline_type = payload.pipeline_type or "generic"
    if payload.pipeline_stage is not None:
        lead.pipeline_stage = payload.pipeline_stage or "novo"
        lead.stage = lead.pipeline_stage
        # EMG-1B: etapa ganha/perdida do funil reflete no status operacional
        from ..models import CrmPipeline, CrmPipelineStage
        st = (
            db.query(CrmPipelineStage)
            .join(CrmPipeline, CrmPipeline.id == CrmPipelineStage.pipeline_id)
            .filter(
                CrmPipelineStage.owner_id == current_user.id,
                CrmPipeline.name == lead.pipeline_type,
                CrmPipelineStage.slug == lead.pipeline_stage,
            )
            .first()
        )
        if st and st.is_won and payload.status is None:
            lead.status = "convertido"
            if not getattr(lead, "converted_at", None):
                lead.converted_at = datetime.now(timezone.utc)
        elif st and st.is_lost and payload.status is None:
            lead.status = "perdido"
    if payload.stage is not None:
        lead.stage = payload.stage
    if payload.tags is not None:
        lead.tags = _normalize_tags(payload.tags)
    if hasattr(lead, "updated_at"):
        lead.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(lead)
    return LeadOut.model_validate(lead)


@router.get("/{lead_id}/notes", response_model=list[LeadNoteOut])
def list_lead_notes(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista notas internas de um lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == current_user.id).first()
    if not lead:
        raise HTTPException(404, "Lead não encontrado")
    notes = (
        db.query(LeadNote)
        .filter(LeadNote.lead_id == lead.id, LeadNote.owner_id == current_user.id)
        .order_by(LeadNote.created_at.desc())
        .all()
    )
    return [LeadNoteOut.model_validate(n) for n in notes]


@router.post("/{lead_id}/notes", response_model=LeadNoteOut, status_code=201)
def create_lead_note(
    lead_id: int,
    payload: LeadNoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cria nota interna. Não envia nada ao WhatsApp."""
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == current_user.id).first()
    if not lead:
        raise HTTPException(404, "Lead não encontrado")
    note = LeadNote(owner_id=current_user.id, lead_id=lead.id, content=payload.content.strip())
    db.add(note)
    if hasattr(lead, "updated_at"):
        lead.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(note)
    return LeadNoteOut.model_validate(note)


@router.delete("/{lead_id}/notes/{note_id}", status_code=204)
def delete_lead_note(
    lead_id: int,
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exclui nota interna do lead."""
    note = (
        db.query(LeadNote)
        .filter(LeadNote.id == note_id, LeadNote.lead_id == lead_id, LeadNote.owner_id == current_user.id)
        .first()
    )
    if not note:
        raise HTTPException(404, "Nota não encontrada")
    db.delete(note)
    db.commit()
    return


@router.delete("/{lead_id}", status_code=204)
def delete_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exclui um lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == current_user.id).first()
    if not lead:
        raise HTTPException(404, "Lead não encontrado")

    # CRM 1.0+: conversas podem apontar para leads via conversations.lead_id.
    # Se apagarmos o lead sem limpar esse vínculo, o PostgreSQL pode bloquear o DELETE
    # por chave estrangeira. Preservamos o histórico da conversa e apenas desvinculamos.
    db.query(Conversation).filter(
        Conversation.lead_id == lead.id
    ).update({Conversation.lead_id: None}, synchronize_session=False)
    db.query(LeadNote).filter(
        LeadNote.lead_id == lead.id,
        LeadNote.owner_id == current_user.id,
    ).delete(synchronize_session=False)
    db.query(CustomFieldValue).filter(
        CustomFieldValue.lead_id == lead.id,
        CustomFieldValue.owner_id == current_user.id,
    ).delete(synchronize_session=False)

    db.delete(lead)
    db.commit()
    return


@router.get("/export/csv")
def export_leads_csv(
    flow_id: Optional[int] = None,
    source: Optional[str] = None,
    tag: Optional[str] = None,
    include_simulator: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exporta leads em CSV, incluindo variáveis do contexto."""
    q = db.query(Lead).filter(Lead.owner_id == current_user.id)
    if flow_id:
        q = q.filter(Lead.flow_id == flow_id)
    if source:
        q = q.filter(Lead.source == source)
    elif include_simulator is False:
        q = q.filter(Lead.source != "simulator")

    leads = q.order_by(Lead.created_at.desc()).all()
    if tag:
        needle = tag.strip().lower()
        leads = [l for l in leads if any(str(t).strip().lower() == needle for t in (l.tags or []))]
    flows_map = {f.id: f.name for f in db.query(Flow).filter(Flow.owner_id == current_user.id).all()}

    all_context_keys = set()
    for l in leads:
        ctx = l.context if isinstance(l.context, dict) else {}
        all_context_keys.update(ctx.keys())
    context_keys = sorted(all_context_keys)

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)

    header = [
        "id", "nome", "telefone", "email", "fluxo", "status", "etapa", "origem",
        "conversation_id", "connection_id", "tags", "valor_venda", "motivo_perda", "convertido_em", "ultima_interacao", "data_criacao",
    ]
    header += context_keys
    writer.writerow(header)

    for l in leads:
        ctx = l.context if isinstance(l.context, dict) else {}
        row = [
            l.id,
            l.name or "",
            l.phone or "",
            l.email or "",
            flows_map.get(l.flow_id, ""),
            l.status or "",
            l.stage or "",
            l.source or "",
            getattr(l, "conversation_id", None) or "",
            getattr(l, "connection_id", None) or "",
            ", ".join(l.tags or []) if getattr(l, "tags", None) else "",
            getattr(l, "deal_value", None) or "",
            getattr(l, "lost_reason", None) or "",
            l.converted_at.isoformat() if getattr(l, "converted_at", None) else "",
            l.last_interaction_at.isoformat() if getattr(l, "last_interaction_at", None) else "",
            l.created_at.isoformat() if l.created_at else "",
        ]
        for key in context_keys:
            row.append(ctx.get(key, ""))
        writer.writerow(row)

    output.seek(0)
    filename = f"leads-dialoga-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
