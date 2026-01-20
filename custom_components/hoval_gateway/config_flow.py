"""Config flow for Hoval Gateway integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_IGNORE_KEYWORDS,
    CONF_UNIT_ID,
    DEFAULT_IGNORE_KEYWORDS,
    DEFAULT_PORT,
    DEFAULT_UNIT_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    host = data[CONF_HOST]
    port = data[CONF_PORT]

    # Test TCP connection using asyncio
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=10
        )
        writer.close()
        await writer.wait_closed()
    except asyncio.TimeoutError as err:
        raise ConnectionError(f"Connection to {host}:{port} timed out") from err
    except OSError as err:
        raise ConnectionError(f"Cannot connect to {host}:{port}: {err}") from err

    return {"title": f"Hoval Gateway ({host})"}


class HovalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hoval Gateway."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Create entry
                return self.async_create_entry(title=info["title"], data=user_input)

        # Show form
        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                vol.Optional(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): cv.positive_int,
                vol.Optional(
                    CONF_IGNORE_KEYWORDS, default=DEFAULT_IGNORE_KEYWORDS
                ): str,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )
