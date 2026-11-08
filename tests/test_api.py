"""Exercise real V2 request and refresh contracts against mock HTTP."""

import asyncio
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import httpx
import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.util.file import WriteError
from solaredge import AsyncMonitoringClient, OAuthToken, SolarEdgeResponseError

from custom_components.solaredge_forecast.api import (
    DurableTokenStore,
    TokenStorage,
    first_history_month,
    measurements,
    midnight,
    monthly_history,
    retry_delay,
    total_kwh,
)


def payload(value=10, unit="KWH", timestamp="2026-01-01T00:00:00Z"):
    return {"unit": unit, "values": [{"timestamp": timestamp, "value": value}]}


@pytest.mark.parametrize("unit,value", [("WH", 1000), ("kwh", 1), ("MWH", 0.001)])
def test_units(unit, value):
    assert total_kwh(payload(value, unit)) == 1


@pytest.mark.parametrize(
    "body",
    [
        {},
        [],
        {"unit": "KWH", "values": []},
        payload(None),
        payload(True),
        payload(float("nan")),
        payload(-1),
        payload(1, "W"),
        {"unit": "KWH", "values": [None]},
    ],
)
def test_invalid_total_is_not_zero(body):
    with pytest.raises(SolarEdgeResponseError):
        total_kwh(body)
    assert total_kwh(payload(0)) == 0


def test_site_metadata_and_dst():
    assert total_kwh({"unit": "KWH", "values": [{"value": 1}]}) == 1
    with pytest.raises(SolarEdgeResponseError):
        measurements(payload(1, timestamp="2026-01-01T00:00:00"))
    assert first_history_month({"installationDate": "2022-12-14"}) == date(2023, 1, 1)
    with pytest.raises(SolarEdgeResponseError):
        first_history_month({})
    zone = ZoneInfo("Europe/Amsterdam")
    assert midnight(date(2026, 3, 29), zone).utcoffset().total_seconds() == 3600
    assert midnight(date(2026, 3, 30), zone).utcoffset().total_seconds() == 7200


async def test_v2_windows_units_and_boundary_deduplication():
    calls = []

    def transport(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "unit": "WH",
                    "values": [
                        {"timestamp": "2019-12-31T23:00:00Z", "value": 1000},
                        {"timestamp": "2022-12-31T23:00:00Z", "value": 9999},
                    ],
                },
            )
        return httpx.Response(200, json=payload(2, timestamp="2022-12-31T23:00:00Z"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        async with AsyncMonitoringClient(
            access_token="test-access", client=http
        ) as client:
            history = await monthly_history(
                client,
                123,
                date(2020, 1, 1),
                date(2026, 1, 1),
                ZoneInfo("Europe/Amsterdam"),
            )
    assert history["energy"]["values"] == [
        {"date": "2020-01-01", "value": 1000},
        {"date": "2023-01-01", "value": 2000},
    ]
    assert len(calls) == 2
    assert calls[0].url.path == "/v2/sites/123/energy"
    assert calls[0].url.params["resolution"] == "MONTH"
    assert calls[0].url.params["unit"] == "KWH"
    assert calls[0].url.params["from"] == "2019-12-31T23:00:00Z"
    assert calls[0].url.params["to"] == calls[1].url.params["from"]
    assert "api_key" not in str(calls[0].url)


async def test_refresh_is_serialized_and_durable_before_requests(hass, entry):
    storage = TokenStorage(hass, entry)
    auth = await storage.async_auth()
    seen = []
    saved = AsyncMock(wraps=storage.store.async_save)
    storage.store.async_save = saved

    async def transport(request):
        seen.append(request)
        if request.url.path.endswith("/oauth2/token"):
            assert request.method == "POST"
            assert b'"grant_type":"refresh_token"' in request.content
            assert b'"refresh_token":"test-refresh"' in request.content
            return httpx.Response(
                200,
                json={
                    "access_token": "rotated-access",
                    "refresh_token": "rotated-refresh",
                    "expires_in": 7200,
                },
            )
        assert saved.await_count == 1
        assert request.headers["Authorization"] == "Bearer rotated-access"
        return httpx.Response(200, json=payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        async with AsyncMonitoringClient(oauth=auth, client=http) as client:
            await asyncio.gather(client.get_energy(123), client.get_energy(123))
    assert sum(r.url.path.endswith("/oauth2/token") for r in seen) == 1
    restarted = await TokenStorage(hass, entry).async_auth()
    assert restarted.token.refresh_token == "rotated-refresh"
    assert "rotated-access" not in repr(restarted)
    assert "rotated-refresh" not in repr(restarted)


async def test_failed_real_store_write_blocks_and_can_retry(hass, entry):
    storage = TokenStorage(hass, entry)
    auth = await storage.async_auth()
    rotated = OAuthToken("new-access", "new-refresh", site_id=123)
    with patch.object(
        storage.store._io,
        "async_write",
        AsyncMock(side_effect=WriteError("test disk failure")),
    ):
        with pytest.raises(OSError, match="did not complete"):
            await storage.async_save(rotated)
    assert storage.pending == rotated
    assert auth.token.access_token == "test-access"
    await storage.async_flush()
    assert storage.pending is None
    assert (await TokenStorage(hass, entry).async_auth()).token == rotated


async def test_401_refresh_and_failed_persistence_sends_no_retry(hass, entry):
    storage = TokenStorage(hass, entry)
    await storage.async_auth()
    token = OAuthToken("valid-access", "valid-refresh", site_id=123)
    await storage.async_save(token)
    auth = await storage.async_auth()
    requests = []

    def transport(request):
        requests.append(request)
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(
                200,
                json={
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "expires_in": 7200,
                },
            )
        return httpx.Response(401, json={"message": "Unauthorized"})

    with patch.object(
        storage.store._io,
        "async_write",
        AsyncMock(side_effect=WriteError("test disk failure")),
    ):
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
            async with AsyncMonitoringClient(oauth=auth, client=http) as client:
                with pytest.raises(OSError):
                    await client.get_energy(123)
    assert len(requests) == 2  # original 401, refresh; no unaudited API retry
    assert storage.pending.refresh_token == "new-refresh"
    await storage.async_flush()
    assert (
        await TokenStorage(hass, entry).async_auth()
    ).token.refresh_token == "new-refresh"


async def test_store_requires_write_acknowledgement(hass):
    store = DurableTokenStore(hass, 1, "test-token", atomic_writes=True, private=True)
    await store.async_save({"refresh_token": "test-value"})
    assert await DurableTokenStore(hass, 1, "test-token").async_load() == {
        "refresh_token": "test-value"
    }


def test_retry_after():
    assert retry_delay(None) == 3600
    assert retry_delay("120") == 120
    assert retry_delay("0") == 60
    assert retry_delay("invalid") == 3600
    assert retry_delay("inf") == 3600
    tomorrow = datetime.now(timezone.utc).timestamp() + 3600
    stamp = datetime.fromtimestamp(tomorrow, timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )
    assert 3595 < retry_delay(stamp) <= 3600


async def test_missing_rotated_refresh_token_requires_reauth(hass, entry):
    storage = TokenStorage(hass, entry)
    auth = await storage.async_auth()
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(
            200, json={"access_token": "new-access", "expires_in": 7200}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        async with AsyncMonitoringClient(oauth=auth, client=http) as client:
            with pytest.raises(ConfigEntryAuthFailed, match="rotated refresh"):
                await client.get_energy(123)
    assert len(requests) == 1
    assert requests[0].url.path.endswith("/oauth2/token")
    with pytest.raises(ConfigEntryAuthFailed):
        await storage.async_flush()
