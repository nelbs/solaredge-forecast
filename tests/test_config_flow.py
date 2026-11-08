"""Entry migration, homeowner consent, options and sensor identities."""

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
import voluptuous as vol
from solaredge import OAuthToken

from custom_components.solaredge_forecast import (
    SolaredgeForecastData,
    _entry_settings,
    async_migrate_entry,
    async_setup_entry,
)
from custom_components.solaredge_forecast.api import DurableTokenStore
from custom_components.solaredge_forecast.config_flow import (
    SolaredgeForecastConfigFlow,
    SolaredgeForecastOptionsFlowHandler,
    _schema,
    _validate_user_input,
)
from custom_components.solaredge_forecast.const import (
    CONF_ACCOUNT_KEY,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_REDIRECT_URI,
    CONF_SITE_ID,
    CONF_TOKEN,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
    SENSOR_TYPES,
)
from custom_components.solaredge_forecast.sensor import SolaredgeForecastSensor

from .conftest import make_entry


def flow_for(hass, settings):
    flow = SolaredgeForecastConfigFlow()
    flow.hass = hass
    flow.settings = settings
    flow.credentials = {
        CONF_CLIENT_ID: "test-app",
        CONF_CLIENT_SECRET: "test-secret",
        CONF_REDIRECT_URI: "http://localhost:8080/oauth/callback",
    }
    return flow


def callback(flow, site_id=123, state=None, uri=None):
    return {
        "callback_url": (
            f"{uri or flow.credentials[CONF_REDIRECT_URI]}?code=test-code"
            f"&site_id={site_id}&state={state or flow.state}"
        )
    }


async def test_new_authorization_creates_v2_entry(hass, settings):
    flow = flow_for(hass, settings)
    token = OAuthToken("test-access", "test-refresh", site_id=123)
    with patch(
        "custom_components.solaredge_forecast.config_flow.async_exchange_code",
        AsyncMock(return_value=token),
    ) as exchange:
        result = await flow.async_step_authorize(callback(flow))
    assert result["type"] == "create_entry"
    assert result["data"][CONF_TOKEN] == token.to_dict()
    assert result["data"][CONF_CLIENT_SECRET] == "test-secret"
    assert flow.VERSION == 2
    exchange.assert_awaited_once_with(
        "test-app",
        "test-secret",
        "test-code",
        redirect_uri="http://localhost:8080/oauth/callback",
        site_id=123,
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"site_id": 124},
        {"state": "mismatch"},
        {"uri": "https://untrusted.invalid/callback"},
    ],
)
async def test_callback_identity_checked_before_token_exchange(hass, settings, bad):
    flow = flow_for(hass, settings)
    with patch(
        "custom_components.solaredge_forecast.config_flow.async_exchange_code",
        AsyncMock(),
    ) as exchange:
        result = await flow.async_step_authorize(callback(flow, **bad))
    assert result["errors"]["base"] == "invalid_auth"
    exchange.assert_not_called()


async def test_manual_callback_can_omit_state(hass, settings):
    flow = flow_for(hass, settings)
    with patch(
        "custom_components.solaredge_forecast.config_flow.async_exchange_code",
        AsyncMock(return_value=OAuthToken("a", "r", site_id=123)),
    ):
        result = await flow.async_step_authorize(
            {
                "callback_url": flow.credentials[CONF_REDIRECT_URI]
                + "?code=x&site_id=123"
            }
        )
    assert result["type"] == "create_entry"


async def test_reauth_retains_options_and_persists_before_reload(hass, entry, settings):
    legacy = SimpleNamespace(
        entry_id=entry.entry_id,
        data={},
        version=1,
        options={**settings, CONF_ACCOUNT_KEY: "obsolete-test-key"},
    )
    flow = flow_for(hass, {})
    flow._get_reauth_entry = Mock(return_value=legacy)
    result = await flow.async_step_reauth({})
    assert result["step_id"] == "auth"
    assert flow.settings[CONF_SITE_ID] == 123
    flow.credentials = {
        CONF_CLIENT_ID: "test-app",
        CONF_CLIENT_SECRET: "test-secret",
        CONF_REDIRECT_URI: "http://localhost:8080/oauth/callback",
    }
    token = OAuthToken("new-access", "new-refresh", site_id=123)
    with patch(
        "custom_components.solaredge_forecast.config_flow.async_exchange_code",
        AsyncMock(return_value=token),
    ):
        result = await flow.async_step_authorize(callback(flow))
    assert result["reason"] == "reauth_successful"
    update = hass.config_entries.async_update_entry.call_args
    assert update.args[0] is legacy
    assert update.kwargs["version"] == 2
    assert CONF_ACCOUNT_KEY not in update.kwargs["data"]
    assert CONF_ACCOUNT_KEY not in update.kwargs["options"]
    assert update.kwargs["options"][CONF_SITE_ID] == 123
    stored = await DurableTokenStore(
        hass, 1, f"{DOMAIN}.{entry.entry_id}.oauth"
    ).async_load()
    assert stored == token.to_dict()
    hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)


async def test_retry_failed_grant_write_does_not_spend_code_twice(
    hass, entry, settings
):
    flow = flow_for(hass, settings)
    flow.reauth_entry = entry
    with (
        patch(
            "custom_components.solaredge_forecast.config_flow.async_exchange_code",
            AsyncMock(return_value=OAuthToken("a", "r", site_id=123)),
        ) as exchange,
        patch.object(
            DurableTokenStore,
            "async_save",
            AsyncMock(side_effect=[OSError("test failure"), None]),
        ),
    ):
        failed = await flow.async_step_authorize(callback(flow))
        assert failed["errors"]["base"] == "cannot_store"
        hass.config_entries.async_reload.assert_not_called()
        retried = await flow.async_step_authorize(callback(flow))
    assert retried["reason"] == "reauth_successful"
    assert exchange.await_count == 1


async def test_migration_keeps_option_only_entry_id(hass, settings):
    legacy = SimpleNamespace(
        version=1,
        entry_id="legacy-id",
        data={},
        options={**settings, CONF_ACCOUNT_KEY: "obsolete-test-key"},
    )
    assert await async_migrate_entry(hass, legacy)
    hass.config_entries.async_update_entry.assert_called_once_with(legacy, version=2)
    assert _entry_settings(legacy)[CONF_SITE_ID] == 123
    assert legacy.entry_id == "legacy-id"
    assert _entry_settings(legacy)[CONF_UPDATE_INTERVAL] == 120


async def test_v1_setup_triggers_reauth(hass, settings):
    from homeassistant.exceptions import ConfigEntryAuthFailed

    legacy = make_entry({}, settings, version=1)
    with pytest.raises(ConfigEntryAuthFailed, match="V2 Site Access"):
        await async_setup_entry(hass, legacy)


def test_options_have_no_credentials_and_interval_is_bounded(settings):
    schema = _schema(settings)
    configured = schema(settings)
    assert CONF_ACCOUNT_KEY not in configured
    assert CONF_CLIENT_SECRET not in configured
    assert configured[CONF_UPDATE_INTERVAL] == 120
    with pytest.raises(vol.Invalid):
        schema({**settings, CONF_UPDATE_INTERVAL: 15})
    assert schema({**settings, CONF_UPDATE_INTERVAL: 60})[CONF_UPDATE_INTERVAL] == 60


async def test_options_reject_switching_authorized_site(hass, entry, settings):
    flow = SolaredgeForecastOptionsFlowHandler()
    flow.hass = hass
    flow.handler = entry.entry_id
    hass.config_entries.async_get_known_entry.return_value = entry
    result = await flow.async_step_user({**settings, CONF_SITE_ID: 999})
    assert result["errors"][CONF_SITE_ID] == "site_change"


def test_forecast_settings_validation_unchanged(settings):
    with patch(
        "custom_components.solaredge_forecast.config_flow.dt_util.now",
        return_value=SimpleNamespace(date=lambda: date(2026, 11, 8)),
    ):
        assert _validate_user_input(settings) == {}


def test_sensor_unique_ids_preserved(entry):
    coordinator = SimpleNamespace(
        unique_id=entry.entry_id,
        data=None,
        last_update_success=True,
        config_entry=entry,
    )
    for description in SENSOR_TYPES:
        sensor = SolaredgeForecastSensor(coordinator, description)
        assert sensor.unique_id == f"preserved-entry_{description.key}"


async def test_reauth_waits_for_old_rotation_then_stops_old_coordinator(
    hass, entry, settings
):
    coordinator = SolaredgeForecastData(hass, entry)
    await coordinator.async_initialize()
    hass.data[DOMAIN] = {entry.entry_id: coordinator}
    started = asyncio.Event()
    release = asyncio.Event()

    async def ongoing_fetch():
        started.set()
        await release.wait()
        await coordinator.tokens.async_save(
            OAuthToken("old-access", "old-rotation", site_id=123)
        )

    coordinator._async_fetch_data = ongoing_fetch
    old_update = asyncio.create_task(coordinator._async_update_data())
    await started.wait()
    flow = flow_for(hass, settings)
    flow.reauth_entry = entry
    with patch(
        "custom_components.solaredge_forecast.config_flow.async_exchange_code",
        AsyncMock(return_value=OAuthToken("new-access", "new-grant", site_id=123)),
    ):
        replacement = asyncio.create_task(flow.async_step_authorize(callback(flow)))
        await asyncio.sleep(0)
        assert not replacement.done()
        release.set()
        await old_update
        assert (await replacement)["reason"] == "reauth_successful"
    stored = await DurableTokenStore(
        hass, 1, f"{DOMAIN}.{entry.entry_id}.oauth"
    ).async_load()
    assert stored["refresh_token"] == "new-grant"
    assert coordinator._shutdown_requested
