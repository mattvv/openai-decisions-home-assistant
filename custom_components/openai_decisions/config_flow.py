"""Config flow: one API key per entry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DecisionsAuthError, DecisionsClient, DecisionsError
from .const import DOMAIN

SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): str})


class OpenAIDecisionsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for an OpenAI API key and check it."""

    VERSION = 1

    async def _check(self, api_key: str) -> str | None:
        try:
            await DecisionsClient(async_get_clientsession(self.hass), api_key).validate()
        except DecisionsAuthError:
            return "invalid_auth"
        except DecisionsError:
            return "cannot_connect"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._async_abort_entries_match({CONF_API_KEY: user_input[CONF_API_KEY]})
            if not (error := await self._check(user_input[CONF_API_KEY])):
                return self.async_create_entry(title="OpenAI Decisions", data=user_input)
            errors["base"] = error
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not (error := await self._check(user_input[CONF_API_KEY])):
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates=user_input
                )
            errors["base"] = error
        return self.async_show_form(step_id="reauth_confirm", data_schema=SCHEMA, errors=errors)
