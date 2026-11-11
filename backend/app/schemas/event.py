
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


EventStatus = Literal[
    "Planned",
    "Ongoing",
    "Completed",
    "Cancelled",
]

EventType = Literal[
    "College Event",
    "Hackathon",
    "Meeting",
    "Holiday",
    "Training",
    "Workshop",
    "Other",
]


class EventBase(BaseModel):

    title: str = Field(
        ...,
        min_length=2,
        max_length=200,
    )

    description: str = Field(
        default="",
        max_length=5000,
    )

    event_type: EventType = "Other"

    start_at: datetime

    end_at: datetime

    venue: str = Field(
        default="",
        max_length=250,
    )

    status: EventStatus = "Planned"

    reminder_minutes: list[int] = Field(
        default_factory=lambda: [1440, 60],
        max_length=10,
    )

    assigned_user_ids: list[str] = Field(
        default_factory=list,
        max_length=100,
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, value):
        value = value.strip()

        if not value:
            raise ValueError("Event title cannot be empty")

        return value

    @field_validator("start_at", "end_at")
    @classmethod
    def validate_datetime(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "Date and time must include a timezone"
            )

        return value

    @field_validator("reminder_minutes")
    @classmethod
    def validate_reminders(cls, values):
        allowed_values = {
            0,
            15,
            30,
            60,
            120,
            360,
            720,
            1440,
            2880,
            10080,
        }

        if any(value not in allowed_values for value in values):
            raise ValueError("Invalid reminder timing")

        if len(values) != len(set(values)):
            raise ValueError("Duplicate reminder timings are not allowed")

        return values

    @field_validator("assigned_user_ids")
    @classmethod
    def validate_assigned_users(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("Duplicate staff assignments are not allowed")

        for user_id in values:
            if not user_id.strip():
                raise ValueError("Invalid staff user ID")

        return values

    @model_validator(mode="after")
    def validate_event_times(self):
        if self.end_at <= self.start_at:
            raise ValueError(
                "Event end time must be after start time"
            )

        return self


class EventCreate(EventBase):
    pass


class EventUpdate(BaseModel):

    title: str | None = Field(
        default=None,
        min_length=2,
        max_length=200,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )

    event_type: EventType | None = None

    start_at: datetime | None = None

    end_at: datetime | None = None

    venue: str | None = Field(
        default=None,
        max_length=250,
    )

    status: EventStatus | None = None

    reminder_minutes: list[int] | None = Field(
        default=None,
        max_length=10,
    )

    assigned_user_ids: list[str] | None = Field(
        default=None,
        max_length=100,
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Event title cannot be empty")

        return value.strip() if value is not None else value

    @field_validator("start_at", "end_at")
    @classmethod
    def validate_datetime(cls, value):
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError(
                "Date and time must include a timezone"
            )

        return value

    @field_validator("reminder_minutes")
    @classmethod
    def validate_reminders(cls, values):
        if values is None:
            return values

        allowed_values = {
            0, 15, 30, 60, 120, 360, 720,
            1440, 2880, 10080,
        }

        if any(value not in allowed_values for value in values):
            raise ValueError("Invalid reminder timing")

        if len(values) != len(set(values)):
            raise ValueError("Duplicate reminder timings are not allowed")

        return values

    @field_validator("assigned_user_ids")
    @classmethod
    def validate_assigned_users(cls, values):
        if values is not None:
            if len(values) != len(set(values)):
                raise ValueError("Duplicate staff assignments are not allowed")

            if any(not user_id.strip() for user_id in values):
                raise ValueError("Invalid staff user ID")

        return values


class EventResponse(BaseModel):

    id: str
    title: str
    description: str
    event_type: str
    start_at: datetime
    end_at: datetime
    venue: str
    status: str
    reminder_minutes: list[int]
    created_by: str
    created_at: datetime
    updated_at: datetime

    assigned_user_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class EventAssignmentResponse(BaseModel):

    id: str
    event_id: str
    user_id: str
    attendance_status: str
    assigned_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EventAttendanceUpdate(BaseModel):

    attendance_status: Literal[
        "Pending",
        "Accepted",
        "Declined",
    ]
