from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CaseCreateRequest(BaseModel):
    title: str
    source: str = "xiaoba_runtime"
    source_session_id: str | None = None
    source_user_id: str | None = None
    summary: str | None = None
    priority: str = "normal"
    labels: list[str] = Field(default_factory=list)
    category: str | None = None
    recommended_next_action: str | None = None


class EventCreateRequest(BaseModel):
    kind: str
    actor_type: str = "agent"
    actor_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class StateUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_state: str = Field(alias="from")
    to: str
    actor_id: str
    reason: str | None = None
    category: str | None = None
    recommended_next_action: str | None = None


class LogEventCreateRequest(BaseModel):
    agent: str
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)


class LogCardCreateRequest(BaseModel):
    agent: str
    card_type: str
    title: str
    summary: str | None = None
    severity: str | None = None
    status: str = "open"
    payload: dict[str, Any] = Field(default_factory=dict)
