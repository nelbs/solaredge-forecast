"""Utility helpers for SolarEdge Forecast."""

from __future__ import annotations

import re

API_KEY_PATTERN = re.compile(r"([?&]api_key=)[^&\s]+", re.IGNORECASE)


def redact_sensitive_values(message: str) -> str:
    """Redact secrets from exception messages before logging."""
    return API_KEY_PATTERN.sub(r"\1***", message)
