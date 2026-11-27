"""Explicit CRM query and mutation policy. Display names never grant access."""
from fastapi import Depends, HTTPException
from sqlalchemy import Text, cast, or_, and_, select, false
from app.core.security import get_current_user
from app.db.database import get_db
from app.models.lead import Lead
from app.models.follow_up import FollowUp
from app.models.user import User


def get_crm_db(actor=Depends(get_current_user), db=Depends(get_db)):
    previous = db.info.get("crm_actor")
    db.info["crm_actor"] = actor
    try:
        yield db
    finally:
        if previous is None:
            db.info.pop("crm_actor", None)
        else:
            db.info["crm_actor"] = previous


def actor(db):
    return db.info.get("crm_actor")


def scoped(db, query, model):
    user = actor(db)
    from app.models.quotation import Quotation
    from app.services.permissions import quotations_allowed
    if model is Lead:
        query = query.where(Lead.deleted_at.is_(None))
    if model is FollowUp:
        query = query.where(FollowUp.lead_id.in_(select(Lead.id).where(Lead.deleted_at.is_(None))))
    if model is Quotation and not quotations_allowed(user):
        return query.where(false())
    if user is not None and user.role == "Staff":
        divisions = tuple(user.lead_access)
        if not divisions:
            return query.where(false())
        if model is Lead:
            return query.where(Lead.division.in_(divisions))
        if model is FollowUp:
            leads = scoped(db, select(Lead.id), Lead)
            owned = leads.where(Lead.assignee_user_id == user.id)
            return query.where(FollowUp.lead_id.in_(leads), or_(FollowUp.assignee_user_id == user.id,
                and_(FollowUp.assignee_user_id.is_(None), FollowUp.lead_id.in_(owned))))
        query = query.where(model.assignee_user_id == user.id)
        if model is Quotation:
            return query.where(Quotation.division.in_(divisions))
        return query.where(or_(*(cast(model.divisions, Text).contains(f'"{division}"') for division in divisions)))
    return query


def require_record(db, record):
    user = actor(db)
    if record is None or (user is not None and user.role == "Staff" and record.assignee_user_id != user.id):
        raise HTTPException(404, "Record not found")
    if user is not None and user.role == "Staff":
        divisions = [record.division] if isinstance(record, Lead) else record.divisions
        if not user.lead_access.keys() & set(divisions):
            raise HTTPException(404, "Record not found")
    return record


def require_lead_creation(db, division):
    user = actor(db)
    if user is not None and user.role == "Staff" and not user.lead_access.get(division, False):
        raise HTTPException(403, "Your administrator has not enabled lead creation for this division")


def require_lead_action(db, division, action):
    user = actor(db)
    if user is not None and user.role == "Staff" and (
        division not in user.lead_access or action not in user.lead_actions.get(division, ())
    ):
        raise HTTPException(403, f"Your administrator has not enabled lead {action} access for this division")


def require_record_division(db, divisions):
    user = actor(db)
    if user is not None and user.role == "Staff" and (not divisions or set(divisions) - user.lead_access.keys()):
        raise HTTPException(403, "Use only your assigned divisions")


def require_admin(db, detail="Only administrators can delete or reassign CRM records"):
    user = actor(db)
    if user is not None and user.role != "Admin":
        raise HTTPException(403, detail)


def creation_assignment(db):
    user = actor(db)
    return user.id if user is not None else None


def enforce_follow_assignment(db, payload):
    user = actor(db)
    if user is not None and user.role == "Staff":
        # This label is presentation only; access always derives from the linked lead ID.
        payload["assigned_to"] = user.name


def follow_assignee_name(db, lead, fallback, assignee_user_id=None):
    effective_id = assignee_user_id or lead.assignee_user_id
    if effective_id:
        user = db.get(User, effective_id)
        if user is not None:
            return user.name
    return fallback


def require_follow_lead(db, lead):
    user = actor(db)
    if lead is None or lead.deleted_at is not None:
        raise HTTPException(404, "Lead not found")
    if user is not None and user.role == "Staff":
        if lead.division not in user.lead_access:
            raise HTTPException(404, "Lead not found")
        if lead.assignee_user_id != user.id and db.scalar(select(FollowUp.id).where(
            FollowUp.lead_id == lead.id, FollowUp.assignee_user_id == user.id,
            FollowUp.deleted_at.is_(None)).limit(1)) is None:
            raise HTTPException(404, "Lead not found")
    return lead


def assign_follow_up(db, lead, payload, current=None):
    """Only admins assign other accounts; IDs, never display names, grant access."""
    user = actor(db)
    requested = payload.get("assignee_user_id")
    if user is not None and user.role == "Staff":
        effective = (current.assignee_user_id or lead.assignee_user_id) if current else user.id
        if requested is not None and requested != effective:
            raise HTTPException(403, "Only administrators can reassign actions")
        requested = effective
    if requested is not None:
        if current is not None and requested == current.assignee_user_id:
            payload["assigned_to"] = current.assigned_to
            return payload
        account = db.scalar(select(User).where(User.id == requested).with_for_update())
        if account is None or not account.is_active or (account.role == "Staff" and lead.division not in account.lead_access):
            raise HTTPException(422, "Select an active account with access to this division")
        payload.update(assignee_user_id=account.id, assigned_to=account.name)
    elif current is None:
        payload["assignee_user_id"] = None
    return payload
