"""Explicit CRM query and mutation policy. Display names never grant access."""
from fastapi import Depends, HTTPException
from sqlalchemy import Text, cast, select, false
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
    if model is Quotation and not quotations_allowed(user):
        return query.where(false())
    if user is not None and user.role == "Staff":
        if model is Lead:
            return query.where(Lead.division == user.lead_division) if user.lead_division else query.where(false())
        if model is FollowUp:
            leads = scoped(db, select(Lead.id), Lead).where(Lead.assignee_user_id == user.id)
            return query.where(FollowUp.lead_id.in_(leads))
        query = query.where(model.assignee_user_id == user.id)
        if user.lead_division:
            if model is Quotation:
                return query.where(Quotation.division == user.lead_division)
            return query.where(cast(model.divisions, Text).contains('"' + user.lead_division + '"'))
        return query
    return query


def require_record(db, record):
    user = actor(db)
    if record is None or (user is not None and user.role == "Staff" and record.assignee_user_id != user.id):
        raise HTTPException(404, "Record not found")
    if user is not None and user.role == "Staff":
        divisions = [record.division] if isinstance(record, Lead) else record.divisions
        if (isinstance(record, Lead) or user.lead_division) and user.lead_division not in divisions:
            raise HTTPException(404, "Record not found")
    return record


def require_lead_creation(db, division):
    user = actor(db)
    if user is not None and user.role == "Staff":
        if not user.can_create_leads or not user.lead_division:
            raise HTTPException(403, "Your administrator has not enabled lead creation")
        if division != user.lead_division:
            raise HTTPException(403, "You can only add leads to your assigned division")


def require_record_division(db, divisions):
    user = actor(db)
    if user is not None and user.role == "Staff" and user.lead_division and user.lead_division not in divisions:
        raise HTTPException(403, "Use your assigned division")


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


def follow_assignee_name(db, lead, fallback):
    if lead.assignee_user_id:
        user = db.get(User, lead.assignee_user_id)
        if user is not None:
            return user.name
    return fallback
