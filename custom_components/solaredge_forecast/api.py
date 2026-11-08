"""V2 production mapping, bounded queries and persistent OAuth rotation."""

from __future__ import annotations

import math
from datetime import date, datetime, time
from email.utils import parsedate_to_datetime
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from solaredge import OAuth2, OAuthToken, SolarEdgeResponseError

from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_SITE_ID, CONF_TOKEN, DOMAIN
from .solaredgeforecast import _add_months, _parse_api_date


class DurableTokenStore(Store[dict[str, Any]]):
    """Require an acknowledged atomic write, not just Store's logged failure."""

    async def async_save(self, data: dict[str, Any]) -> None:
        self.write_completed = False
        await super().async_save(data)
        if not self.write_completed:
            raise OSError("SolarEdge token storage write did not complete")

    async def _async_write_data(self, data: dict) -> None:
        # Store.async_save swallows WriteError; acknowledge only the actual disk write.
        await super()._async_write_data(data)
        self.write_completed = True


class TokenStorage:
    """Save each single-use refresh token before the next API request."""

    def __init__(self, hass, entry) -> None:
        self.entry = entry
        self.store = DurableTokenStore(
            hass,
            1,
            f"{DOMAIN}.{entry.entry_id}.oauth",
            private=True,
            atomic_writes=True,
        )
        self.pending: OAuthToken | None = None
        self.last_refresh_token: str | None = None
        self.invalid_rotation = False

    async def async_auth(self) -> OAuth2:
        """Load the authoritative token, moving initial grants out of entry data."""
        saved = await self.store.async_load()
        if saved is None:
            saved = self.entry.data.get(CONF_TOKEN)
            if saved is None:
                raise ValueError("Site Access authorization is required")
            await self.store.async_save(saved)
        token = OAuthToken.from_dict(saved)
        if not token.refresh_token:
            raise ValueError("Site Access refresh token is missing")
        self.last_refresh_token = token.refresh_token
        site_id = self.entry.options.get(
            CONF_SITE_ID, self.entry.data.get(CONF_SITE_ID)
        )
        if token.site_id != int(site_id):
            raise ValueError("Stored Site Access grant belongs to another site")
        if not self.entry.data.get(CONF_CLIENT_ID) or not self.entry.data.get(
            CONF_CLIENT_SECRET
        ):
            raise ValueError("Site Access app credentials are missing")
        return OAuth2(
            token,
            client_id=self.entry.data[CONF_CLIENT_ID],
            client_secret=self.entry.data[CONF_CLIENT_SECRET],
            on_token_update=self.async_save,
        )

    async def async_save(self, token: OAuthToken) -> None:
        """Persist rotation immediately; retain failed writes for the next attempt."""
        if not token.refresh_token or token.refresh_token == self.last_refresh_token:
            self.invalid_rotation = True
            raise ConfigEntryAuthFailed(
                "SolarEdge did not return a rotated refresh token"
            )
        self.pending = token
        await self.async_flush()

    async def async_flush(self) -> None:
        """Never continue using a rotated grant until its write succeeds."""
        if self.invalid_rotation:
            raise ConfigEntryAuthFailed("SolarEdge refresh token rotation failed")
        if self.pending is not None:
            await self.store.async_save(self.pending.to_dict())
            self.last_refresh_token = self.pending.refresh_token
            self.pending = None


def midnight(value: date, timezone: ZoneInfo) -> datetime:
    """Return a site-local midnight, including DST transitions."""
    return datetime.combine(value, time.min, tzinfo=timezone)


def _energy_values(
    payload: dict[str, Any],
) -> list[tuple[dict[str, Any], float | None]]:
    """Validate V2 energy units and samples independently of bucket timestamps."""
    if not isinstance(payload, dict):
        raise SolarEdgeResponseError("Invalid V2 production response")
    factors = {"WH": 0.001, "KWH": 1, "MWH": 1000}
    unit = str(payload.get("unit", "")).upper()
    values = payload.get("values")
    if unit not in factors or not isinstance(values, list):
        raise SolarEdgeResponseError("Invalid V2 production measurements")
    result = []
    for item in values:
        if not isinstance(item, dict) or "value" not in item:
            raise SolarEdgeResponseError("Invalid V2 production sample")
        value = item["value"]
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise SolarEdgeResponseError("Invalid V2 production sample")
        result.append((item, None if value is None else value * factors[unit]))
    return result


def measurements(payload: dict[str, Any]) -> list[tuple[datetime, float | None]]:
    """Require timestamped monthly buckets; totals need no bucket timestamp."""
    result = []
    for item, value in _energy_values(payload):
        try:
            timestamp = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError
        except (KeyError, TypeError, ValueError, AttributeError) as err:
            raise SolarEdgeResponseError("Invalid V2 production timestamp") from err
        result.append((timestamp, value))
    return result


def total_kwh(payload: dict[str, Any]) -> float:
    """Read a TOTAL production response without treating missing data as zero."""
    values = _energy_values(payload)
    if len(values) != 1 or values[0][1] is None:
        raise SolarEdgeResponseError("V2 returned no total production")
    return values[0][1]


async def monthly_history(client, site_id: int, start: date, end: date, timezone):
    """Fetch complete months in non-overlapping windows of at most three years."""
    values = []
    seen: set[date] = set()
    current = start
    while current < end:
        stop = min(_add_months(current, 36), end)
        response = await client.get_energy(
            site_id,
            start=midnight(current, timezone),
            end=midnight(stop, timezone),
            resolution="MONTH",
            unit="KWH",
        )
        for timestamp, value in measurements(response):
            local_date = timestamp.astimezone(timezone).date()
            if current <= local_date < stop:
                if local_date.day != 1 or local_date in seen:
                    raise SolarEdgeResponseError("Invalid or duplicate V2 month bucket")
                seen.add(local_date)
                values.append(
                    {
                        "date": local_date.isoformat(),
                        "value": None if value is None else value * 1000,
                    }
                )
        current = stop
    if not values:
        raise SolarEdgeResponseError("V2 returned no historical production")
    return {"energy": {"values": values}}


def first_history_month(details: dict[str, Any]) -> date:
    """V2 has no dataPeriod: omit the partial installation month."""
    installation = details.get("installationDate")
    if not installation:
        raise SolarEdgeResponseError(
            "V2 installationDate is missing; set the production start date in options"
        )
    try:
        installed = _parse_api_date(installation)
    except ValueError as err:
        raise SolarEdgeResponseError("Invalid V2 installationDate") from err
    return _add_months(installed.replace(day=1), 1)


def retry_delay(value: str | None) -> float:
    """Respect both Retry-After formats; monthly quota failures back off an hour."""
    if value is None:
        return 3600
    try:
        delay = float(value)
        return max(60, delay) if math.isfinite(delay) else 3600
    except ValueError:
        try:
            return max(
                60,
                parsedate_to_datetime(value).timestamp() - datetime.now().timestamp(),
            )
        except TypeError, ValueError, OverflowError:
            return 3600
