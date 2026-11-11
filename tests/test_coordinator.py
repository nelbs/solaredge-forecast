"""Credit-saving cache lifecycle, site timezone and explicit failure behavior."""

import time
from datetime import date, datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from solaredge import SolarEdgeAuthError, SolarEdgeRateLimitError

from custom_components.solaredge_forecast import SolaredgeForecastData
from custom_components.solaredge_forecast.const import CONF_STARTDATE_PRODUCTION

from .conftest import make_entry
from .test_forecast import constant_history


@pytest.fixture
def client():
    api = AsyncMock()
    api.__aenter__.return_value = api
    api.get_site_details.return_value = {
        "siteId": 123,
        "installationDate": "2022-12-14",
        "location": {"timezone": "Europe/Amsterdam"},
    }
    api.get_energy.return_value = {
        "unit": "KWH",
        "values": [{"timestamp": "2026-01-01T00:00:00Z", "value": 1900}],
    }
    return api


async def test_first_refresh_uses_iso_installation_date_without_production_start(
    hass, entry, client
):
    entry = make_entry({**entry.data, CONF_STARTDATE_PRODUCTION: ""})
    client.get_site_details.return_value["installationDate"] = "2022-12-14T00:00:00Z"
    now = datetime(2026, 11, 8, 20, tzinfo=ZoneInfo("Europe/Amsterdam"))
    coordinator = SolaredgeForecastData(hass, entry)
    await coordinator.async_initialize()
    with (
        patch(
            "custom_components.solaredge_forecast.AsyncMonitoringClient",
            return_value=client,
        ),
        patch(
            "custom_components.solaredge_forecast.monthly_history",
            AsyncMock(return_value=constant_history()),
        ) as history,
        patch("custom_components.solaredge_forecast.dt_util.now", return_value=now),
    ):
        result = await coordinator._async_update_data()
    history.assert_awaited_once_with(
        client, 123, date(2023, 1, 1), date(2026, 11, 1), now.tzinfo
    )
    assert result.startdate_production == date(2023, 1, 1)
    assert result.solaredge_produced == 1900


async def test_cache_persists_across_restart_and_refreshes_on_rollover(
    hass, entry, client
):
    now = datetime(2026, 11, 8, 20, tzinfo=ZoneInfo("Europe/Amsterdam"))
    coordinator = SolaredgeForecastData(hass, entry)
    await coordinator.async_initialize()
    with (
        patch(
            "custom_components.solaredge_forecast.AsyncMonitoringClient",
            return_value=client,
        ),
        patch(
            "custom_components.solaredge_forecast.monthly_history",
            AsyncMock(return_value=constant_history()),
        ) as history,
        patch(
            "custom_components.solaredge_forecast.dt_util.now", return_value=now
        ) as clock,
    ):
        await coordinator._async_update_data()
        assert history.await_count == 1
        assert client.get_site_details.await_count == 1
        assert client.get_energy.await_count == 2
        for call in client.get_energy.call_args_list:
            assert call.kwargs["end"] == now
            assert call.kwargs["start"].tzinfo.key == "Europe/Amsterdam"
            assert call.kwargs["resolution"] == "TOTAL"
        second = SolaredgeForecastData(hass, entry)
        await second.async_initialize()
        await second._async_update_data()
        assert history.await_count == 1
        assert client.get_site_details.await_count == 1
        assert client.get_energy.await_count == 4
        clock.return_value = datetime(2027, 1, 1, 12, tzinfo=now.tzinfo)
        result = await second._async_update_data()
        assert history.await_count == 2
        assert result.startdate.year == 2027
        second.cache["saved_at"] = time.time() - 8 * 86400
        await second._async_update_data()
        assert history.await_count == 3


async def test_quota_backoff_avoids_calls_and_reports_unavailable(hass, entry, client):
    coordinator = SolaredgeForecastData(hass, entry)
    await coordinator.async_initialize()
    client.get_site_details.side_effect = SolarEdgeRateLimitError(
        "test quota",
        status_code=429,
        retry_after="120",
    )
    with patch(
        "custom_components.solaredge_forecast.AsyncMonitoringClient",
        return_value=client,
    ):
        with pytest.raises(UpdateFailed, match="credit or rate"):
            await coordinator._async_update_data()
        with pytest.raises(UpdateFailed, match="backoff"):
            await coordinator._async_update_data()
    assert client.get_site_details.await_count == 1
    assert 115 <= coordinator.retry_at - time.time() <= 120


async def test_auth_failure_requests_reauth_without_success_fallback(
    hass, entry, client
):
    coordinator = SolaredgeForecastData(hass, entry)
    await coordinator.async_initialize()
    client.get_site_details.side_effect = SolarEdgeAuthError(
        "test denial", status_code=403
    )
    with patch(
        "custom_components.solaredge_forecast.AsyncMonitoringClient",
        return_value=client,
    ):
        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()


async def test_pacing_covers_http_and_token_requests(hass, entry):
    coordinator = SolaredgeForecastData(hass, entry)
    with (
        patch("custom_components.solaredge_forecast.time.monotonic", return_value=100),
        patch(
            "custom_components.solaredge_forecast.asyncio.sleep", AsyncMock()
        ) as sleep,
    ):
        await coordinator._async_pace_request(None)
        assert sleep.await_args.args[0] == 0
        await coordinator._async_pace_request(None)
        assert sleep.await_args.args[0] == pytest.approx(6.1)
