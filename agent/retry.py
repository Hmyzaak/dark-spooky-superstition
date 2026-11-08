"""Pomocné funkce pro omezené opakování HTTP požadavků."""

import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


MAX_RETRIES = 5
MAX_HTTP_TIMEOUT_SECONDS = 300
MAX_RETRY_DELAY_SECONDS = 30
RETRYABLE_HTTP_STATUS_CODES = {408, 429}


def validate_http_settings(timeout: float, max_retries: int) -> None:
    """Ověří timeout a počet opakování HTTP požadavků."""

    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
        or timeout > MAX_HTTP_TIMEOUT_SECONDS
    ):
        raise ValueError(
            f"Timeout musí být větší než 0 a nejvýše {MAX_HTTP_TIMEOUT_SECONDS} sekund."
        )

    if (
        isinstance(max_retries, bool)
        or not isinstance(max_retries, int)
        or not 0 <= max_retries <= MAX_RETRIES
    ):
        raise ValueError(f"max_retries musí být celé číslo od 0 do {MAX_RETRIES}.")


def is_retryable_http_status(status_code: int) -> bool:
    """Vrátí, zda má smysl opakovat požadavek pro daný HTTP status."""

    return status_code in RETRYABLE_HTTP_STATUS_CODES or 500 <= status_code <= 599


def get_retry_delay(attempt: int, retry_after: str | None = None) -> float:
    """Určí omezenou prodlevu; přednost má platná hlavička Retry-After."""

    if retry_after:
        value = retry_after.strip()
        try:
            seconds = float(value)
            if math.isfinite(seconds):
                return min(MAX_RETRY_DELAY_SECONDS, max(0.0, seconds))
        except ValueError:
            pass

        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
            return min(MAX_RETRY_DELAY_SECONDS, max(0.0, seconds))
        except (TypeError, ValueError, OverflowError):
            pass

    return float(min(2**attempt, MAX_RETRY_DELAY_SECONDS))
