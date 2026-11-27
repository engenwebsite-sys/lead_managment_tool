from typing import Annotated
from app.schemas.pagination import Page, FollowUpList
from app.services.pagination import collection_query, paginate
from app.services.concurrency import claim_version
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.crm_access import actor, get_crm_db, scoped, require_follow_lead, assign_follow_up
from app.services.crm_access import follow_assignee_name
from app.services.activity import entry, snapshot
from app.models.user import User
from app.db.operations import database_operation
from app.models.follow_up import FollowUp
from app.models.lead import Lead
from app.schemas.follow_up import FollowUpCreate, FollowUpResponse, FollowUpUpdate, FollowUpUpdateResponse

router = APIRouter(prefix="/api/follow-ups", tags=["Follow-ups"])


def utc_now():
    return datetime.now(timezone.utc)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def event(message, at):
    return {"id": str(uuid.uuid4()), "at": at.isoformat(), "message": message}


def response(item, db):
    lead = db.get(Lead, item.lead_id)
    if lead is None:
        raise HTTPException(status_code=409, detail="The linked lead is unavailable")
    payload = {column.name: getattr(item, column.name) for column in item.__table__.columns}
    for field in ["due_at", "created_at", "updated_at", "completed_at", "deleted_at"]:
        if payload[field] is not None:
            payload[field] = utc(payload[field])
    payload.update(customer_id=lead.customer_id, customer=lead.customer, division=lead.division,
                   referred_by=lead.referred_by, lead_source=lead.lead_source, opportunity_name=lead.opportunity_name)
    payload["assigned_to"] = follow_assignee_name(db, lead, item.assigned_to, item.assignee_user_id)
    return FollowUpResponse.model_validate(payload)


def responses(rows, db):
    if not rows:
        return []
    # Keep batch-loaded entities alive while rendering to avoid per-row queries.
    leads = db.scalars(select(Lead).where(Lead.id.in_({row.lead_id for row in rows}))).all()
    from app.models.user import User
    ids = {lead.assignee_user_id for lead in leads if lead.assignee_user_id} | {row.assignee_user_id for row in rows if row.assignee_user_id}
    users = db.scalars(select(User).where(User.id.in_(ids))).all()
    return [response(row, db) for row in rows]


def find(db, follow_up_id, lock=False):
    query = scoped(db, select(FollowUp), FollowUp).where(FollowUp.id == follow_up_id, FollowUp.deleted_at.is_(None))
    if lock:
        query = query.with_for_update()
    item = db.scalar(query.execution_options(populate_existing=True))
    if item is None:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    if lock:
        lead = db.scalar(select(Lead).where(Lead.id == item.lead_id).with_for_update().execution_options(populate_existing=True))
        if lead is None or lead.deleted_at is not None:
            raise HTTPException(404, "Lead not found")
    return item


@router.post("", response_model=FollowUpResponse, status_code=status.HTTP_201_CREATED)
def create_follow_up(data: FollowUpCreate, db: Session = Depends(get_crm_db)):
    with database_operation(db):
        lead = require_follow_lead(db, db.scalar(select(Lead).where(Lead.id == data.lead_id).with_for_update().execution_options(populate_existing=True)))
        payload = data.model_dump(by_alias=False)
        assign_follow_up(db, lead, payload)
        payload["due_at"] = utc(data.due_at)
        item = FollowUp(**payload, history=[entry(db, f"Scheduled {data.type.lower()} for {payload['due_at'].isoformat()}.", at=utc_now())])
        db.add(item)
        db.commit()
        db.refresh(item)
        return response(item, db)


@router.get("/assignees")
def assignees(leadId: str, db: Session = Depends(get_crm_db)):
    with database_operation(db):
        lead = require_follow_lead(db, db.get(Lead, leadId))
        user = actor(db)
        if user is not None and user.role == "Staff":
            return [{"id": user.id, "name": user.name}]
        accounts = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.name, User.id)).all()
        return [{"id": account.id, "name": account.name} for account in accounts
                if account.role == "Admin" or lead.division in account.lead_access]


def list_items(db, *, view="All", filters=None):
    filters = filters or FollowUpList()
    query = collection_query(db, FollowUp, filters, utc_now())
    if view != "All":
        query = query.where(FollowUp.status == "Pending")
        query = query.where(FollowUp.due_at < utc_now()) if view == "Overdue" else query.where(FollowUp.due_at >= utc_now())
    return paginate(db, query, FollowUp, filters, lambda item: response(item, db), render_many=lambda rows: responses(rows, db))


@router.get("", response_model=list[FollowUpResponse] | Page[FollowUpResponse])
def get_follow_ups(db: Session = Depends(get_crm_db), filters: Annotated[FollowUpList, Query()] = FollowUpList()):
    with database_operation(db):
        return list_items(db, filters=filters)


@router.get("/upcoming", response_model=list[FollowUpResponse] | Page[FollowUpResponse])
def upcoming_follow_ups(db: Session = Depends(get_crm_db), filters: Annotated[FollowUpList, Query()] = FollowUpList()):
    with database_operation(db):
        return list_items(db, view="Upcoming", filters=filters)


@router.get("/overdue", response_model=list[FollowUpResponse] | Page[FollowUpResponse])
def overdue_follow_ups(db: Session = Depends(get_crm_db), filters: Annotated[FollowUpList, Query()] = FollowUpList()):
    with database_operation(db):
        return list_items(db, view="Overdue", filters=filters)


@router.get("/{follow_up_id}", response_model=FollowUpResponse)
def get_follow_up(follow_up_id: str, db: Session = Depends(get_crm_db)):
    with database_operation(db):
        return response(find(db, follow_up_id), db)


@router.put("/{follow_up_id}", response_model=FollowUpUpdateResponse)
def update_follow_up(follow_up_id: str, data: FollowUpUpdate, db: Session = Depends(get_crm_db)):
    with database_operation(db):
        item = find(db, follow_up_id, lock=True)
        was_completed = item.status == "Completed"
        user = actor(db)
        updates = data.model_dump(exclude_unset=True, by_alias=False)
        details = {"purpose", "type", "assigned_to", "assignee_user_id", "priority", "reminder_minutes", "notes"}
        tracked = details | {"due_at", "status", "outcome", "completion_notes", "completed_at"}
        before = snapshot(item, tracked)
        if was_completed:
            if data.status == "Pending" or data.next_due_at is not None:
                raise HTTPException(409, "Completed actions stay closed. Schedule a separate new action")
            if user is not None and user.role == "Staff" and not user.can_edit_follow_ups:
                raise HTTPException(403, "Your administrator has not enabled follow-up editing")
        claim_version(db, FollowUp, item, data.expected_version)
        at = utc_now()
        history = list(item.history)
        next_item = None
        completing = data.status == "Completed" and not was_completed
        if completing:
            if not data.outcome or not data.completion_notes:
                raise HTTPException(status_code=422, detail="Completion requires an outcome and discussion notes")
            item.status = "Completed"
            item.completed_at = at
            item.outcome = data.outcome
            item.completion_notes = data.completion_notes
            message = f"Completed · {data.outcome}. {data.completion_notes}"
            if data.next_due_at is not None:
                due_at = utc(data.next_due_at)
                if due_at <= at:
                    db.rollback()
                    raise HTTPException(status_code=422, detail="The next follow-up must be in the future")
                next_item = FollowUp(lead_id=item.lead_id, purpose=item.purpose, type=item.type, assignee_user_id=item.assignee_user_id,
                    due_at=due_at, assigned_to=item.assigned_to, priority=item.priority,
                    reminder_minutes=item.reminder_minutes, notes="",
                    history=[event(f"Scheduled next follow-up for {due_at.isoformat()}.", at)])
                db.add(next_item)
        else:
            if not was_completed and (data.next_due_at is not None or data.outcome is not None or data.completion_notes is not None or data.completed_at is not None):
                raise HTTPException(status_code=422, detail="Outcome and next-follow-up fields are only accepted when completing a task")
            if user is not None and user.role == "Staff":
                updates.pop("assigned_to", None)
                if not user.can_edit_follow_ups and any(updates[key] != getattr(item, key) for key in details & updates.keys()):
                    raise HTTPException(403, "Your administrator has not enabled follow-up editing")
            if "assignee_user_id" in updates:
                assign_follow_up(db, db.get(Lead, item.lead_id), updates, current=item)
            else:
                updates.pop("assigned_to", None)
            if not was_completed and data.due_at is not None and utc(data.due_at) != utc(item.due_at):
                if not data.reschedule_reason or utc(data.due_at) <= at:
                    raise HTTPException(status_code=422, detail="Rescheduling requires a future time and a reason")
                message = f"Rescheduled from {utc(item.due_at).isoformat()} to {utc(data.due_at).isoformat()}. Reason: {data.reschedule_reason}"
            else:
                message = "Completed action corrected." if was_completed else "Follow-up details updated."
            if was_completed:
                if data.completion_notes is not None and not data.completion_notes.strip():
                    raise HTTPException(422, "Completion notes cannot be empty")
                if data.completed_at is not None and utc(data.completed_at) > at:
                    raise HTTPException(422, "Completion date cannot be in the future")
            editable = details | {"due_at"} | ({"outcome", "completion_notes", "completed_at"} if was_completed else set())
            for field in editable & updates.keys():
                setattr(item, field, utc(updates[field]) if field in {"due_at", "completed_at"} else updates[field])
        history.append(entry(db, message, before, snapshot(item, tracked), at))
        item.history = history
        db.commit()
        db.refresh(item)
        if next_item is not None:
            db.refresh(next_item)
        return FollowUpUpdateResponse(record=response(item, db), next_follow_up=response(next_item, db) if next_item else None)


@router.delete("/{follow_up_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_follow_up(follow_up_id: str, db: Session = Depends(get_crm_db), expectedVersion: Annotated[int | None, Query(ge=1)] = None):
    with database_operation(db):
        user = actor(db)
        if user is not None and user.role == "Staff" and not user.can_delete_follow_ups:
            raise HTTPException(403, "Your administrator has not enabled follow-up deletion")
        item = find(db, follow_up_id, lock=True)
        claim_version(db, FollowUp, item, expectedVersion)
        item.deleted_at = utc_now()
        item.history = [*item.history, entry(db, "Follow-up archived.", at=item.deleted_at)]
        db.commit()
