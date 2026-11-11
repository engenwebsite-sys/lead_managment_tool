
from datetime import datetime, timezone
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.operations import database_operation
from app.models.events import Event, EventAssignment
from app.models.user import User
from app.schemas.event import (
    EventCreate,
    EventUpdate,
    EventResponse,
    EventAttendanceUpdate,
)
from app.services.crm_access import get_crm_db, actor


router = APIRouter(
    prefix="/api/events",
    tags=["Calendar & Events"],
)


# --------------------------------------------------
# DATE / TIME HELPERS
# --------------------------------------------------

def utc_now():
    return datetime.now(timezone.utc)


def normalize_input_datetime(value: datetime) -> datetime:
    """
    Validate incoming datetime and convert it to UTC.
    Incoming API datetimes must contain a timezone.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(
            status_code=422,
            detail="Date and time must include a timezone",
        )

    return value.astimezone(timezone.utc)


def normalize_db_datetime(value: datetime) -> datetime:
    """
    Database drivers such as SQLite may return naive datetimes.
    Our application stores these timestamps as UTC.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def get_current_actor(db):
    user = actor(db)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    return user


def require_admin(db):
    user = get_current_actor(db)

    if user.role != "Admin":
        raise HTTPException(
            status_code=403,
            detail="Only administrators can manage events",
        )

    return user


# --------------------------------------------------
# EVENT ACCESS
# --------------------------------------------------

def find_event(db, event_id, lock=False):
    user = get_current_actor(db)

    query = select(Event).where(Event.id == event_id)

    # Staff can only access events assigned to them.
    if user.role == "Staff":
        query = query.where(
            Event.id.in_(
                select(EventAssignment.event_id).where(
                    EventAssignment.user_id == user.id
                )
            )
        )

    if lock:
        query = query.with_for_update()

    item = db.scalar(
        query.execution_options(populate_existing=True)
    )

    if item is None:
        raise HTTPException(
            status_code=404,
            detail="Event not found",
        )

    return item


# --------------------------------------------------
# EVENT RESPONSE
# --------------------------------------------------

def event_payload(item, db):
    assignments = db.scalars(
        select(EventAssignment).where(
            EventAssignment.event_id == item.id
        )
    ).all()

    payload = {
        column.name: getattr(item, column.name)
        for column in item.__table__.columns
    }

    payload["start_at"] = normalize_db_datetime(item.start_at)
    payload["end_at"] = normalize_db_datetime(item.end_at)
    payload["created_at"] = normalize_db_datetime(item.created_at)
    payload["updated_at"] = normalize_db_datetime(item.updated_at)

    payload["assigned_user_ids"] = [
        assignment.user_id
        for assignment in assignments
    ]

    return EventResponse.model_validate(payload)


# --------------------------------------------------
# STAFF ASSIGNMENT VALIDATION
# --------------------------------------------------

def validate_staff_assignments(db, user_ids):
    if not user_ids:
        return

    unique_ids = set(user_ids)

    users = db.scalars(
        select(User).where(
            User.id.in_(unique_ids),
            User.role == "Staff",
            User.is_active.is_(True),
        )
    ).all()

    if len(users) != len(unique_ids):
        raise HTTPException(
            status_code=422,
            detail=(
                "One or more assigned users are invalid, "
                "inactive, or are not Staff members"
            ),
        )


# --------------------------------------------------
# SCHEDULE CONFLICT VALIDATION
# --------------------------------------------------

def validate_schedule(
    db,
    user_ids,
    start_at,
    end_at,
    exclude_event_id=None,
):
    if not user_ids:
        return

    query = (
        select(EventAssignment)
        .join(
            Event,
            Event.id == EventAssignment.event_id,
        )
        .where(
            EventAssignment.user_id.in_(set(user_ids)),
            Event.status != "Cancelled",
            Event.start_at < end_at,
            Event.end_at > start_at,
        )
    )

    if exclude_event_id:
        query = query.where(
            Event.id != exclude_event_id
        )

    conflicts = db.scalars(query).all()

    if conflicts:
        raise HTTPException(
            status_code=409,
            detail=(
                "One or more staff members already have "
                "another event scheduled during this time"
            ),
        )


# --------------------------------------------------
# SAVE STAFF ASSIGNMENTS
# Preserve existing attendance confirmations.
# --------------------------------------------------

def save_assignments(db, event_id, user_ids):
    existing = db.scalars(
        select(EventAssignment).where(
            EventAssignment.event_id == event_id
        )
    ).all()

    existing_by_user = {
        assignment.user_id: assignment
        for assignment in existing
    }

    requested_ids = set(user_ids)

    # Remove only users who are no longer assigned.
    for user_id, assignment in existing_by_user.items():
        if user_id not in requested_ids:
            db.delete(assignment)

    # Add only newly assigned users.
    for user_id in requested_ids:
        if user_id not in existing_by_user:
            db.add(
                EventAssignment(
                    event_id=event_id,
                    user_id=user_id,
                    attendance_status="Pending",
                )
            )


# --------------------------------------------------
# CREATE EVENT
# --------------------------------------------------

@router.post(
    "",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_event(
    data: EventCreate,
    response: Response,
    db: Session = Depends(get_crm_db),
):
    with database_operation(db):
        user = require_admin(db)

        start_at = normalize_input_datetime(data.start_at)
        end_at = normalize_input_datetime(data.end_at)

        if end_at <= start_at:
            raise HTTPException(
                status_code=422,
                detail="Event end time must be after start time",
            )

        validate_staff_assignments(
            db,
            data.assigned_user_ids,
        )

        if data.status != "Cancelled":
            validate_schedule(
                db,
                data.assigned_user_ids,
                start_at,
                end_at,
            )

        payload = data.model_dump(
            exclude={"assigned_user_ids"}
        )

        payload["start_at"] = start_at
        payload["end_at"] = end_at

        item = Event(
            **payload,
            created_by=user.id,
        )

        db.add(item)
        db.flush()

        save_assignments(
            db,
            item.id,
            data.assigned_user_ids,
        )

        db.commit()
        db.refresh(item)

        response.headers["Cache-Control"] = "no-store"

        return event_payload(item, db)


# --------------------------------------------------
# GET ALL EVENTS
# --------------------------------------------------

@router.get(
    "",
    response_model=list[EventResponse],
)
def get_events(
    response: Response,
    db: Session = Depends(get_crm_db),
    start_date: Annotated[datetime | None, Query()] = None,
    end_date: Annotated[datetime | None, Query()] = None,
    event_status: Annotated[str | None, Query(alias="status")] = None,
):
    with database_operation(db):
        user = get_current_actor(db)

        query = select(Event)

        if user.role == "Staff":
            query = query.where(
                Event.id.in_(
                    select(EventAssignment.event_id).where(
                        EventAssignment.user_id == user.id
                    )
                )
            )

        normalized_start = (
            normalize_input_datetime(start_date)
            if start_date is not None
            else None
        )

        normalized_end = (
            normalize_input_datetime(end_date)
            if end_date is not None
            else None
        )

        if normalized_start is not None:
            query = query.where(
                Event.end_at >= normalized_start
            )

        if normalized_end is not None:
            query = query.where(
                Event.start_at <= normalized_end
            )

        if (
            normalized_start is not None
            and normalized_end is not None
            and normalized_end < normalized_start
        ):
            raise HTTPException(
                status_code=422,
                detail="End date must be after start date",
            )

        if event_status:
            allowed = {
                "Planned",
                "Ongoing",
                "Completed",
                "Cancelled",
            }

            if event_status not in allowed:
                raise HTTPException(
                    status_code=422,
                    detail="Invalid event status",
                )

            query = query.where(
                Event.status == event_status
            )

        items = db.scalars(
            query.order_by(Event.start_at.asc()).limit(500)
        ).all()

        response.headers["Cache-Control"] = "no-store"

        return [
            event_payload(item, db)
            for item in items
        ]


# --------------------------------------------------
# UPCOMING EVENTS
# --------------------------------------------------

@router.get(
    "/upcoming",
    response_model=list[EventResponse],
)
def upcoming_events(
    response: Response,
    db: Session = Depends(get_crm_db),
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    with database_operation(db):
        user = get_current_actor(db)

        query = select(Event).where(
            Event.start_at >= utc_now(),
            Event.status == "Planned",
        )

        if user.role == "Staff":
            query = query.where(
                Event.id.in_(
                    select(EventAssignment.event_id).where(
                        EventAssignment.user_id == user.id
                    )
                )
            )

        items = db.scalars(
            query.order_by(Event.start_at.asc()).limit(limit)
        ).all()

        response.headers["Cache-Control"] = "no-store"

        return [
            event_payload(item, db)
            for item in items
        ]


# --------------------------------------------------
# GET SINGLE EVENT
# --------------------------------------------------

@router.get(
    "/{event_id}",
    response_model=EventResponse,
)
def get_event(
    event_id: str,
    response: Response,
    db: Session = Depends(get_crm_db),
):
    with database_operation(db):
        item = find_event(db, event_id)

        response.headers["Cache-Control"] = "no-store"

        return event_payload(item, db)


# --------------------------------------------------
# UPDATE EVENT
# --------------------------------------------------

@router.put(
    "/{event_id}",
    response_model=EventResponse,
)
def update_event(
    event_id: str,
    data: EventUpdate,
    response: Response,
    db: Session = Depends(get_crm_db),
):
    with database_operation(db):
        require_admin(db)

        item = find_event(db, event_id, lock=True)

        if item.status in ("Completed", "Cancelled"):
            raise HTTPException(
                status_code=409,
                detail="Completed or cancelled events cannot be edited",
            )

        updates = data.model_dump(exclude_unset=True)

        # All model fields are non-nullable.
        for field, value in updates.items():
            if value is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"{field} cannot be null",
                )

        user_ids = updates.pop(
            "assigned_user_ids",
            None,
        )

        start_at = normalize_db_datetime(item.start_at)
        end_at = normalize_db_datetime(item.end_at)

        if "start_at" in updates:
            start_at = normalize_input_datetime(
                updates["start_at"]
            )

        if "end_at" in updates:
            end_at = normalize_input_datetime(
                updates["end_at"]
            )

        if end_at <= start_at:
            raise HTTPException(
                status_code=422,
                detail="Event end time must be after start time",
            )

        if user_ids is not None:
            validate_staff_assignments(
                db,
                user_ids,
            )

            current_ids = list(user_ids)

        else:
            current_ids = [
                assignment.user_id
                for assignment in db.scalars(
                    select(EventAssignment).where(
                        EventAssignment.event_id == item.id
                    )
                ).all()
            ]

        final_status = updates.get(
            "status",
            item.status,
        )

        if final_status != "Cancelled":
            validate_schedule(
                db,
                current_ids,
                start_at,
                end_at,
                exclude_event_id=item.id,
            )

        # Update assignments only when explicitly supplied.
        if user_ids is not None:
            save_assignments(
                db,
                item.id,
                user_ids,
            )

        for field, value in updates.items():
            if field in ("start_at", "end_at"):
                value = normalize_input_datetime(value)

            setattr(item, field, value)

        item.updated_at = utc_now()

        db.commit()
        db.refresh(item)

        response.headers["Cache-Control"] = "no-store"

        return event_payload(item, db)


# --------------------------------------------------
# STAFF ATTENDANCE CONFIRMATION
# --------------------------------------------------

@router.patch(
    "/{event_id}/attendance",
)
def update_attendance(
    event_id: str,
    data: EventAttendanceUpdate,
    response: Response,
    db: Session = Depends(get_crm_db),
):
    with database_operation(db):
        user = get_current_actor(db)

        item = find_event(
            db,
            event_id,
            lock=True,
        )

        if item.status == "Cancelled":
            raise HTTPException(
                status_code=409,
                detail="Cancelled events cannot receive attendance confirmations",
            )

        assignment = db.scalar(
            select(EventAssignment)
            .where(
                EventAssignment.event_id == item.id,
                EventAssignment.user_id == user.id,
            )
            .with_for_update()
        )

        if assignment is None:
            raise HTTPException(
                status_code=403,
                detail="You are not assigned to this event",
            )

        assignment.attendance_status = data.attendance_status

        db.commit()

        response.headers["Cache-Control"] = "no-store"

        return {
            "message": "Attendance updated successfully",
            "event_id": item.id,
            "attendance_status": assignment.attendance_status,
        }


# --------------------------------------------------
# DELETE EVENT
# --------------------------------------------------

@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_event(
    event_id: str,
    db: Session = Depends(get_crm_db),
):
    with database_operation(db):
        require_admin(db)

        item = find_event(
            db,
            event_id,
            lock=True,
        )

        db.delete(item)
        db.commit()

        return Response(status_code=status.HTTP_204_NO_CONTENT)
