"""
Fase C.1 — Agenda interna.

Primeira versão de agendamentos sem Google Calendar.
Permite criar/listar/editar/excluir agendamentos vinculados a leads e fluxos.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import AgendaBlock, AgendaHoliday, Appointment, Flow, Lead, User
from ..schemas import AppointmentCreate, AppointmentUpdate, AppointmentOut
from ..services import google_calendar_service as gcal


router = APIRouter()

PIPELINE_RULES = {
    "generic": {"solicitado": "agendamento_pendente", "confirmado": "agendado", "realizado": "realizado", "nao_compareceu": "no_show", "cancelado": "cancelado"},
    "clinica": {"solicitado": "agendamento_pendente", "confirmado": "avaliacao_marcada", "realizado": "compareceu", "nao_compareceu": "no_show", "cancelado": "cancelado"},
    "petshop": {"solicitado": "agendamento_pendente", "confirmado": "banho_tosa_marcado", "realizado": "atendido", "nao_compareceu": "no_show", "cancelado": "cancelado"},
    "veiculos": {"solicitado": "agendamento_pendente", "confirmado": "visita_marcada", "realizado": "compareceu", "nao_compareceu": "no_show", "cancelado": "cancelado"},
    "suporte_tecnico": {"solicitado": "agendamento_pendente", "confirmado": "agendado", "realizado": "resolvido", "nao_compareceu": "no_show", "cancelado": "cancelado"},
    "Funil Emagrecentro": {"solicitado": "lead_novo", "confirmado": "agendou_avaliacao", "realizado": "compareceu", "nao_compareceu": "nao_compareceu", "cancelado": "reativacao"},
}


def _pipeline_type_from_appointment_type(appointment_type: str | None) -> str:
    mapping = {
        "avaliacao": "clinica",
        "consulta": "clinica",
        "banho_tosa": "petshop",
        "visita": "veiculos",
        "test_drive": "veiculos",
        "suporte": "suporte_tecnico",
    }
    return mapping.get(appointment_type or "", "generic")


def _try_sync_google_calendar(db: Session, owner_id: int, appt: Appointment):
    """Sincroniza com Google se houver conexão ativa. Nunca quebra o CRUD da agenda."""
    conn = gcal.get_connection(db, owner_id)
    if conn and conn.status == "connected":
        gcal.sync_appointment(db, owner_id, appt)


def _hhmm(dt: datetime) -> str:
    local = dt
    return f"{local.hour:02d}:{local.minute:02d}"


def _time_in_range(hhmm: str, start: str, end: str) -> bool:
    return (start or "00:00") <= hhmm < (end or "23:59")


def _assert_slot_free(db: Session, user: User, scheduled_at: datetime, unit_name: str | None):
    """Recusa horário em feriado ou bloqueio da unidade."""
    unit = (unit_name or "").strip()
    day = scheduled_at.date()
    hhmm = _hhmm(scheduled_at)
    weekday = scheduled_at.weekday()  # 0=segunda

    holidays = db.query(AgendaHoliday).filter(AgendaHoliday.owner_id == user.id).all()
    for h in holidays:
        if not h.date:
            continue
        if h.date.date() != day:
            continue
        hun = (h.unit_name or "").strip()
        if hun and unit and hun.lower() != unit.lower():
            continue
        raise HTTPException(400, f"Unidade fechada neste dia ({h.name}).")

    blocks = db.query(AgendaBlock).filter(AgendaBlock.owner_id == user.id).all()
    for b in blocks:
        bun = (b.unit_name or "").strip()
        if bun and unit and bun.lower() != unit.lower():
            continue
        if b.date and b.date.date() != day:
            continue
        if b.weekday is not None and b.date is None and int(b.weekday) != weekday:
            continue
        if _time_in_range(hhmm, b.start_time or "00:00", b.end_time or "23:59"):
            raise HTTPException(400, f"Horário bloqueado ({b.reason or 'bloqueio de agenda'}).")


def _apply_lead_tags(lead: Lead, *names: str):
    tags = list(lead.tags or [])
    lower = {str(t).strip().lower() for t in tags}
    for name in names:
        if name.lower() not in lower:
            tags.append(name)
            lower.add(name.lower())
    lead.tags = tags


def _sync_lead_pipeline_from_appointment(lead: Lead | None, appt: Appointment):
    if not lead:
        return
    ptype = lead.pipeline_type or _pipeline_type_from_appointment_type(appt.appointment_type)
    if ptype == "generic" and appt.appointment_type:
        ptype = _pipeline_type_from_appointment_type(appt.appointment_type)
    if (lead.pipeline_type or "") == "Funil Emagrecentro":
        ptype = "Funil Emagrecentro"
    lead.pipeline_type = ptype
    stage = PIPELINE_RULES.get(ptype, PIPELINE_RULES["generic"]).get(appt.status)
    if stage:
        lead.pipeline_stage = stage
        lead.stage = stage
    if appt.status == "confirmado":
        _apply_lead_tags(lead, "Agendou")
    elif appt.status == "realizado":
        _apply_lead_tags(lead, "Compareceu")
    elif appt.status == "nao_compareceu":
        _apply_lead_tags(lead, "Não compareceu")


def _now():
    return datetime.now(timezone.utc)


def _owned_lead(db: Session, lead_id: Optional[int], user: User) -> Optional[Lead]:
    if not lead_id:
        return None
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == user.id).first()
    if not lead:
        raise HTTPException(404, "Lead não encontrado.")
    return lead


def _owned_flow(db: Session, flow_id: Optional[int], user: User) -> Optional[Flow]:
    if not flow_id:
        return None
    flow = db.query(Flow).filter(Flow.id == flow_id, Flow.owner_id == user.id).first()
    if not flow:
        raise HTTPException(404, "Fluxo não encontrado.")
    return flow


def _owned_appointment(db: Session, appointment_id: int, user: User) -> Appointment:
    appt = db.query(Appointment).filter(Appointment.id == appointment_id, Appointment.owner_id == user.id).first()
    if not appt:
        raise HTTPException(404, "Agendamento não encontrado.")
    return appt


def _serialize(db: Session, appt: Appointment) -> AppointmentOut:
    lead = db.query(Lead).filter(Lead.id == appt.lead_id).first() if appt.lead_id else None
    flow = db.query(Flow).filter(Flow.id == appt.flow_id).first() if appt.flow_id else None
    data = AppointmentOut.model_validate(appt).model_dump()
    data["lead_name"] = lead.name if lead else None
    data["lead_phone"] = lead.phone if lead else None
    data["flow_name"] = flow.name if flow else None
    return AppointmentOut(**data)


@router.get("", response_model=list[AppointmentOut])
def list_appointments(
    status: Optional[str] = None,
    lead_id: Optional[int] = None,
    unit_name: Optional[str] = None,
    flow_id: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista agendamentos com filtros opcionais."""
    q = db.query(Appointment).filter(Appointment.owner_id == current_user.id)
    if status:
        q = q.filter(Appointment.status == status)
    if lead_id:
        q = q.filter(Appointment.lead_id == lead_id)
    if flow_id:
        q = q.filter(Appointment.flow_id == flow_id)
    if unit_name:
        q = q.filter(Appointment.unit_name == unit_name)
    if date_from:
        q = q.filter(Appointment.scheduled_at >= date_from)
    if date_to:
        q = q.filter(Appointment.scheduled_at <= date_to)
    appts = q.order_by(Appointment.scheduled_at.asc()).all()
    return [_serialize(db, a) for a in appts]


@router.post("", response_model=AppointmentOut, status_code=201)
def create_appointment(
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cria agendamento interno."""
    lead = _owned_lead(db, payload.lead_id, current_user)
    flow = _owned_flow(db, payload.flow_id, current_user)
    flow_id = payload.flow_id or (lead.flow_id if lead else None)
    if flow_id and not flow:
        flow = _owned_flow(db, flow_id, current_user)

    _assert_slot_free(db, current_user, payload.scheduled_at, payload.unit_name)

    appt = Appointment(
        owner_id=current_user.id,
        lead_id=lead.id if lead else None,
        flow_id=flow_id,
        title=payload.title,
        scheduled_at=payload.scheduled_at,
        status=payload.status or "solicitado",
        appointment_type=payload.appointment_type or "generic",
        notes=payload.notes,
        unit_name=(payload.unit_name or "").strip() or None,
        calendar_sync_status="not_synced",
    )
    db.add(appt)
    db.flush()
    _sync_lead_pipeline_from_appointment(lead, appt)
    _try_sync_google_calendar(db, current_user.id, appt)
    db.commit()
    db.refresh(appt)
    return _serialize(db, appt)


@router.get("/{appointment_id}", response_model=AppointmentOut)
def get_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _serialize(db, _owned_appointment(db, appointment_id, current_user))


@router.put("/{appointment_id}", response_model=AppointmentOut)
def update_appointment(
    appointment_id: int,
    payload: AppointmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    appt = _owned_appointment(db, appointment_id, current_user)
    data = payload.model_dump(exclude_unset=True)

    if "lead_id" in data:
        lead = _owned_lead(db, data["lead_id"], current_user)
        appt.lead_id = lead.id if lead else None
        if lead and not appt.flow_id:
            appt.flow_id = lead.flow_id
    if "flow_id" in data:
        flow = _owned_flow(db, data["flow_id"], current_user)
        appt.flow_id = flow.id if flow else None
    if "title" in data and data["title"] is not None:
        appt.title = data["title"]
    if "scheduled_at" in data and data["scheduled_at"] is not None:
        appt.scheduled_at = data["scheduled_at"]
    if "unit_name" in data:
        appt.unit_name = (data["unit_name"] or "").strip() or None
    new_when = data.get("scheduled_at") or appt.scheduled_at
    new_unit = appt.unit_name
    if "scheduled_at" in data or "unit_name" in data:
        _assert_slot_free(db, current_user, new_when, new_unit)
    if "status" in data and data["status"] is not None:
        appt.status = data["status"]
    if "appointment_type" in data and data["appointment_type"] is not None:
        appt.appointment_type = data["appointment_type"] or "generic"
    if "notes" in data:
        appt.notes = data["notes"]
    appt.updated_at = _now()
    lead_for_pipeline = db.query(Lead).filter(Lead.id == appt.lead_id, Lead.owner_id == current_user.id).first() if appt.lead_id else None
    _sync_lead_pipeline_from_appointment(lead_for_pipeline, appt)
    _try_sync_google_calendar(db, current_user.id, appt)

    db.commit()
    db.refresh(appt)
    return _serialize(db, appt)


@router.delete("/{appointment_id}", status_code=204)
def delete_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    appt = _owned_appointment(db, appointment_id, current_user)
    db.delete(appt)
    db.commit()
    return
