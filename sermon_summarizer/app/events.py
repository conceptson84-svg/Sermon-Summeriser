"""Shared enums/value types for the app layer."""

from __future__ import annotations

import enum


class ServiceState(enum.Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
