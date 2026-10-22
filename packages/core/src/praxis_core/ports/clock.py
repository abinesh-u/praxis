"""Clock port for decoupled, testable time handling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """Protocol for accessing the current time."""

    def now(self) -> datetime:
        """Return current timezone-aware UTC datetime."""
        ...


class SystemClock:
    """Default production clock using actual system time in UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """Test clock that can be frozen, set to specific moments, or advanced."""

    def __init__(self, initial_time: datetime | None = None) -> None:
        self._current_time = initial_time or datetime.now(UTC)
        if self._current_time.tzinfo is None:
            self._current_time = self._current_time.replace(tzinfo=UTC)

    def now(self) -> datetime:
        return self._current_time

    def advance(self, delta: timedelta) -> None:
        """Advance frozen clock by timedelta."""
        self._current_time += delta

    def set_time(self, when: datetime) -> None:
        """Explicitly set frozen clock to a specific time."""
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        self._current_time = when
