from datetime import datetime, time
import re
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, field_validator, model_validator


class AlertInput(BaseModel):
    id: str
    severity: Literal["critical", "warning", "info"]
    service: str
    group: str
    description: str | None = None
    timestamp: datetime
    labels: dict[str, str] = {}

    @field_validator("timestamp")
    @classmethod
    def must_be_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamp must include timezone info")
        return v


class ActiveHours(BaseModel):
    timezone: str
    start: str
    end: str

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError:
            raise ValueError(f"unknown timezone: {v}")
        return v

    @field_validator("start", "end")
    @classmethod
    def valid_hhmm(cls, v: str) -> str:
        if not re.fullmatch(r"\d{2}:\d{2}", v):
            raise ValueError("must be HH:MM format")
        h, m = int(v[:2]), int(v[3:])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("invalid time value")
        return v


class RouteConditions(BaseModel):
    severity: list[str] | None = None
    service: list[str] | None = None
    group: list[str] | None = None
    labels: dict[str, str] | None = None


class RouteTarget(BaseModel):
    type: Literal["slack", "email", "pagerduty", "webhook"]
    channel: str | None = None
    address: str | None = None
    service_key: str | None = None
    url: str | None = None
    headers: dict[str, str] | None = None

    @model_validator(mode="after")
    def required_type_fields(self) -> "RouteTarget":
        required = {"slack": "channel", "email": "address", "pagerduty": "service_key", "webhook": "url"}
        field = required[self.type]
        if getattr(self, field) is None:
            raise ValueError(f"target type '{self.type}' requires '{field}'")
        return self


class RouteInput(BaseModel):
    id: str
    conditions: RouteConditions
    target: RouteTarget
    priority: int
    suppression_window_seconds: int = 0
    active_hours: ActiveHours | None = None

    @field_validator("suppression_window_seconds")
    @classmethod
    def non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("suppression_window_seconds must be >= 0")
        return v
