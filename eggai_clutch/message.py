from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ClutchState(BaseModel):
    clutch_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    strategy: str = "sequential"
    members: list[str] = Field(default_factory=list)
    turn: int = 0
    history: list[dict[str, Any]] = Field(default_factory=list)


class ClutchContext(Generic[T]):
    """Internal context - hidden from users."""

    def __init__(
        self,
        data: T,
        source: str = "input",
        state: ClutchState | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.data = data
        self.source = source
        self.state = state or ClutchState()
        self.metadata = metadata or {}

    def next(self, source: str, data: T) -> ClutchContext[T]:
        new_state = ClutchState(
            clutch_id=self.state.clutch_id,
            strategy=self.state.strategy,
            members=self.state.members,
            turn=self.state.turn + 1,
            history=self.state.history + [{"source": self.source, "data": _serialize(self.data)}],
        )
        return ClutchContext(
            data=data,
            source=source,
            state=new_state,
            metadata=self.metadata.copy(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "data": _serialize(self.data),
            "source": self.source,
            "state": self.state.model_dump(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ClutchContext:
        return cls(
            data=raw["data"],
            source=raw["source"],
            state=ClutchState(**raw["state"]),
            metadata=raw.get("metadata", {}),
        )


def _serialize(data: Any) -> Any:
    if isinstance(data, BaseModel):
        return data.model_dump()
    return data


_current_context: ContextVar[ClutchContext | None] = ContextVar("clutch_context", default=None)


def get_context() -> ClutchContext:
    ctx = _current_context.get()
    if ctx is None:
        raise RuntimeError("No active Clutch context")
    return ctx


def set_context(ctx: ClutchContext | None):
    _current_context.set(ctx)
