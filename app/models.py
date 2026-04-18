from datetime import datetime
from typing import Literal
from pydantic import BaseModel, field_validator


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
