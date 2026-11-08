"""Real Home Assistant runtime objects, with no live services."""

from datetime import datetime, timezone
from types import MappingProxyType
from unittest.mock import AsyncMock, Mock

import homeassistant  # noqa: F401 -- HA must install its httpx alias before HTTP imports.
import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.solaredge_forecast.const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_ENDDAY,
    CONF_ENDMONTH,
    CONF_REDIRECT_URI,
    CONF_SITE_ID,
    CONF_STARTDATE_PRODUCTION,
    CONF_STARTDAY,
    CONF_STARTMONTH,
    CONF_TOKEN,
    DOMAIN,
)


@pytest.fixture
def settings():
    return {
        CONF_SITE_ID: 123,
        CONF_STARTDAY: 1,
        CONF_STARTMONTH: "January",
        CONF_ENDDAY: 31,
        CONF_ENDMONTH: "December",
        CONF_STARTDATE_PRODUCTION: "01012023",
    }


@pytest.fixture
async def hass(tmp_path):
    instance = HomeAssistant(str(tmp_path))
    instance.config_entries = Mock()
    instance.config_entries.async_entries.return_value = []
    instance.config_entries.async_reload = AsyncMock(return_value=True)
    yield instance
    await instance.async_block_till_done()


def make_entry(data, options=None, version=2):
    return ConfigEntry(
        data=data,
        options=options or {},
        domain=DOMAIN,
        entry_id="preserved-entry",
        title="SolarEdge Forecast 123",
        version=version,
        minor_version=1,
        source="user",
        unique_id="123",
        discovery_keys=MappingProxyType({}),
        subentries_data=[],
    )


@pytest.fixture
def entry(settings):
    return make_entry(
        {
            **settings,
            CONF_CLIENT_ID: "test-app",
            CONF_CLIENT_SECRET: "test-secret",
            CONF_REDIRECT_URI: "http://localhost:8080/oauth/callback",
            CONF_TOKEN: {
                "access_token": "test-access",
                "refresh_token": "test-refresh",
                "expires_at": datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp(),
                "site_id": 123,
            },
        }
    )
