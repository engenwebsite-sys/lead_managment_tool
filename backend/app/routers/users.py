from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.services.permissions import resolve_role_permissions
from app.core.security import get_current_user, now, passwords
from app.db.database import get_db
from app.db.operations import database_operation
from app.models.user import AuthSession, User, UserAuditEvent
from app.schemas.user import ManagedUser, UserCreate, UserDirectory, UserUpdate

router = APIRouter(prefix="/api/users", tags=["Users & access"])


def require_owner(user: User = Depends(get_current_user)):
    if not user.is_owner or user.role != "Admin":
        raise HTTPException(403, "Only the first administrator (Owner) can manage accounts")
    return user


def snapshot(user):
    return {"name": user.name, "email": user.email, "role": user.role, "isActive": user.is_active,
            "leadDivision": user.lead_division, "canCreateLeads": user.can_create_leads,
            "leadAccess": user.lead_access, "version": user.version}


def validate_lead_access(role, division, can_create):
    if (division is not None and role != "Staff") or (can_create and (role != "Staff" or division is None)):
        raise HTTPException(422, "Lead creation access requires a Staff account with an assigned division")


def resolve_lead_access(changes, role, target=None):
    legacy_fields = {"lead_division", "can_create_leads"}
    if "lead_access" in changes:
        if legacy_fields & changes.keys():
            raise HTTPException(422, "Send either leadAccess or the legacy division fields")
        access = changes.pop("lead_access")
        if access and role != "Staff":
            raise HTTPException(422, "Division permissions apply only to Staff accounts")
        # A previous server version can represent only a single division.
        division, can_create = next(iter(access.items())) if len(access) == 1 else (None, False)
        changes.update(lead_division_access=access, lead_division=division, can_create_leads=can_create)
        return

    if target is not None and role == "Admin" and target.role != role:
        changes.setdefault("lead_division", None)
        changes.setdefault("can_create_leads", False)
    if target is not None and len(target.lead_access) > 1 and role == "Staff" and legacy_fields & changes.keys():
        raise HTTPException(409, "Use division permissions to edit an account with multiple divisions")
    if legacy_fields & changes.keys():
        division = changes.get("lead_division", target.lead_division if target else None)
        can_create = changes.get("can_create_leads", target.can_create_leads if target and division else False)
        validate_lead_access(role, division, can_create)
        changes.update(lead_division_access=None, lead_division=division, can_create_leads=can_create)


def can_read(actor, target):
    return actor.is_owner or actor.id == target.id or (actor.role == "Admin" and target.role == "Staff")


@router.get("", response_model=UserDirectory)
def list_users(response: Response, actor: User = Depends(get_current_user), db: Session = Depends(get_db)):
    with database_operation(db):
        query = select(User)
        if not actor.is_owner:
            query = query.where(User.role == "Staff") if actor.role == "Admin" else query.where(User.id == actor.id)
        users = db.scalars(query.order_by(User.is_owner.desc(), User.role.asc(), User.name.asc())).all()
        response.headers["Cache-Control"] = "no-store"
        return UserDirectory(users=[ManagedUser.model_validate(resolve_role_permissions(db, item)) for item in users], canManageUsers=actor.is_owner, canManageRolePermissions=actor.role == "Admin",
                             adminCount=db.scalar(select(func.count()).select_from(User).where(User.role == "Admin")) if actor.is_owner else None,
                             scope="All accounts" if actor.is_owner else "Staff only" if actor.role == "Admin" else "My profile")


@router.get("/{user_id}", response_model=ManagedUser)
def get_user(user_id: str, response: Response, actor: User = Depends(get_current_user), db: Session = Depends(get_db)):
    with database_operation(db):
        target = db.get(User, user_id)
        if target is None or not can_read(actor, target):
            raise HTTPException(404, "Account not found")
        response.headers["Cache-Control"] = "no-store"
        return resolve_role_permissions(db, target)


@router.post("", status_code=201, response_model=ManagedUser)
def create_user(data: UserCreate, actor: User = Depends(require_owner), db: Session = Depends(get_db)):
    with database_operation(db):
        access = data.model_dump(exclude_unset=True, include={"lead_access", "lead_division", "can_create_leads"})
        resolve_lead_access(access, data.role)
        if data.role == "Admin" and db.scalar(select(User.id).where(User.admin_slot == 2)) is not None:
            raise HTTPException(409, "Maximum two Admin accounts allowed. Demote the second administrator before adding another")
        item = User(name=data.name, email=data.email, role=data.role, admin_slot=2 if data.role == "Admin" else None,
                    password_hash=passwords.hash(data.password), **access)
        db.add(item)
        db.flush()
        db.add(UserAuditEvent(actor_id=actor.id, target_id=item.id, action="Account created", changes={"after": snapshot(item)}))
        db.commit()
        db.refresh(item)
        return resolve_role_permissions(db, item)


@router.put("/{user_id}", response_model=ManagedUser)
def update_user(user_id: str, data: UserUpdate, actor: User = Depends(require_owner), db: Session = Depends(get_db)):
    with database_operation(db):
        target = db.get(User, user_id)
        if target is None:
            raise HTTPException(404, "Account not found")
        if target.is_owner:
            raise HTTPException(403, "The Owner account is protected and cannot be modified here")
        if target.version != data.expected_version:
            raise HTTPException(409, "Account changed in another session. Reload users and try again")
        changes = data.model_dump(exclude_unset=True, by_alias=False)
        changes.pop("expected_version")
        raw_password = changes.pop("password", None)
        role = changes.get("role", target.role)
        resolve_lead_access(changes, role, target)
        if role == "Admin" and db.scalar(select(User.id).where(User.admin_slot == 2, User.id != target.id)) is not None:
            raise HTTPException(409, "Maximum two Admin accounts allowed")
        before = snapshot(target)
        revoke = raw_password is not None or any(
            key in changes and changes[key] != getattr(target, key)
            for key in ("email", "role", "is_active", "lead_division", "can_create_leads")
        )
        if "lead_division_access" in changes and changes["lead_division_access"] is not None:
            revoke = revoke or changes["lead_division_access"] != target.lead_access
        changes.update(admin_slot=2 if role == "Admin" else None, version=target.version + 1)
        if role != target.role:
            changes["quotation_access"] = False
        if raw_password is not None:
            changes["password_hash"] = passwords.hash(raw_password)
        changed = db.execute(update(User).where(User.id == user_id, User.version == data.expected_version)
                             .values(**changes).execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "Account changed in another session. Reload users and try again")
        if revoke:
            db.execute(update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)).values(revoked_at=now()))
        db.refresh(target)
        db.add(UserAuditEvent(actor_id=actor.id, target_id=target.id, action="Account updated",
                             changes={"before": before, "after": snapshot(target), "passwordChanged": raw_password is not None,
                                      "sessionsRevoked": revoke}))
        db.commit()
        return resolve_role_permissions(db, target)


@router.put("/{user_id}/quotation-access", deprecated=True)
def retired_individual_access(user_id: str, actor: User = Depends(get_current_user)):
    if actor.role != "Admin":
        raise HTTPException(403, "Only administrators can manage permissions")
    raise HTTPException(410, "Individual permissions were replaced by Settings > Roles & permissions")
