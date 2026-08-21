from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ContextLifecycleObservation:
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)


class ContextObserver(Protocol):
    def emit(self, event: ContextLifecycleObservation) -> None: ...


class NullContextObserver:
    def emit(self, event: ContextLifecycleObservation) -> None:
        return None


def observe(
    observer: ContextObserver | None,
    event_type: str,
    **payload: Any,
) -> None:
    if observer is None:
        return
    try:
        observer.emit(ContextLifecycleObservation(event_type=event_type, payload=payload))
    except Exception:
        # Instrumentation must never change context-management behavior.
        return
