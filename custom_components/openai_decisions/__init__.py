"""OpenAI Decisions: ask fast yes/no, choice and score questions about camera frames."""

from __future__ import annotations

import logging
import mimetypes
import time
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components.camera import async_get_image
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import DecisionsAuthError, DecisionsClient, DecisionsError, DecisionsQuotaError
from .const import (
    ATTR_CAMERAS,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_IMAGE_PATHS,
    ATTR_MODEL,
    ATTR_QUESTIONS,
    ATTR_TEXT,
    ATTR_TIMEOUT,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    SERVICE_DECIDE,
)
from .decisions import InvalidQuestion, build_payload, image_part, normalize_questions, parse_answers

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type DecisionsConfigEntry = ConfigEntry[DecisionsClient]

DECIDE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_QUESTIONS): vol.All(cv.ensure_list, [dict]),
        vol.Optional(ATTR_TEXT): cv.string,
        vol.Optional(ATTR_CAMERAS): cv.entity_ids,
        vol.Optional(ATTR_IMAGE_PATHS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_MODEL, default=DEFAULT_MODEL): cv.string,
        vol.Optional(ATTR_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(
            vol.Coerce(float), vol.Range(min=1, max=120)
        ),
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the decide action."""

    async def decide(call: ServiceCall) -> ServiceResponse:
        entry = _get_entry(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        timeout: float = call.data[ATTR_TIMEOUT]
        try:
            questions = normalize_questions(call.data[ATTR_QUESTIONS])
        except InvalidQuestion as err:
            raise ServiceValidationError(str(err)) from err

        images = []
        for entity_id in call.data.get(ATTR_CAMERAS, []):
            try:
                image = await async_get_image(hass, entity_id, timeout=int(min(timeout, 30)))
            except HomeAssistantError as err:
                raise HomeAssistantError(f"could not get an image from {entity_id}: {err}") from err
            images.append(image_part(image.content, image.content_type))
        for path in call.data.get(ATTR_IMAGE_PATHS, []):
            images.append(await hass.async_add_executor_job(_read_image, hass, path))

        try:
            payload = build_payload(call.data[ATTR_MODEL], questions, call.data.get(ATTR_TEXT), images)
        except InvalidQuestion as err:
            raise ServiceValidationError(str(err)) from err

        started = time.monotonic()
        try:
            body = await entry.runtime_data.decide(payload, timeout)
        except DecisionsAuthError as err:
            entry.async_start_reauth(hass)
            raise HomeAssistantError(f"OpenAI rejected the API key: {err}") from err
        except DecisionsQuotaError as err:
            raise HomeAssistantError(f"OpenAI quota or rate limit: {err}") from err
        except DecisionsError as err:
            raise HomeAssistantError(f"OpenAI Decisions request failed: {err}") from err
        elapsed_ms = round((time.monotonic() - started) * 1000)
        _LOGGER.debug("decisions answered in %s ms: %s", elapsed_ms, body.get("answers"))

        return {
            "answers": parse_answers(body),
            "model": body.get("model", call.data[ATTR_MODEL]),
            "usage": body.get("usage"),
            "elapsed_ms": elapsed_ms,
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_DECIDE,
        decide,
        schema=DECIDE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    return True


def _get_entry(hass: HomeAssistant, entry_id: str | None) -> DecisionsConfigEntry:
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(f"no {DOMAIN} config entry {entry_id}")
    else:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError("OpenAI Decisions is not set up")
        entry = entries[0]
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(f"{entry.title} is not loaded")
    return entry


def _read_image(hass: HomeAssistant, path: str) -> dict[str, str]:
    if not hass.config.is_allowed_path(path):
        raise ServiceValidationError(f"{path} is not in allowlist_external_dirs")
    content_type = mimetypes.guess_type(path)[0] or "image/jpeg"
    if not content_type.startswith("image/"):
        raise ServiceValidationError(f"{path} is not an image")
    try:
        return image_part(Path(path).read_bytes(), content_type)
    except OSError as err:
        raise HomeAssistantError(f"could not read {path}: {err}") from err


async def async_setup_entry(hass: HomeAssistant, entry: DecisionsConfigEntry) -> bool:
    """Check the key and store a client."""
    client = DecisionsClient(async_get_clientsession(hass), entry.data[CONF_API_KEY])
    try:
        await client.validate()
    except DecisionsAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except DecisionsError as err:
        raise ConfigEntryNotReady(str(err)) from err
    entry.runtime_data = client
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DecisionsConfigEntry) -> bool:
    """Nothing to tear down."""
    return True
