"""Config flow and the decide action."""

from http import HTTPStatus
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.components.camera import Image
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.openai_decisions.const import API_BASE, DOMAIN

MODELS = f"{API_BASE}/models"
DECISIONS = f"{API_BASE}/decisions"


@pytest.fixture
async def entry(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(MODELS, json={"data": []})
    e = MockConfigEntry(domain=DOMAIN, data={CONF_API_KEY: "sk-test"})
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    assert e.state is ConfigEntryState.LOADED
    return e


async def test_flow_success(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(MODELS, json={"data": []})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "sk-good"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_API_KEY: "sk-good"}


async def test_flow_invalid_key(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(MODELS, status=HTTPStatus.UNAUTHORIZED, json={"error": {"message": "bad key"}})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "sk-bad"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_setup_auth_failed(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(MODELS, status=HTTPStatus.UNAUTHORIZED, json={})
    e = MockConfigEntry(domain=DOMAIN, data={CONF_API_KEY: "sk-old"})
    e.add_to_hass(hass)
    await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    assert e.state is ConfigEntryState.SETUP_ERROR
    assert any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())


async def test_decide_with_camera(hass: HomeAssistant, aioclient_mock, entry):
    aioclient_mock.post(
        DECISIONS,
        json={"answers": [{"type": "predicate", "name": "package", "probability": 0.92}], "usage": {"input_tokens": 900}},
    )
    with patch(
        "custom_components.openai_decisions.async_get_image",
        return_value=Image("image/jpeg", b"\xff\xd8"),
    ):
        result = await hass.services.async_call(
            DOMAIN,
            "decide",
            {
                "camera_entity_id": "camera.porch",
                "text": "Porch",
                "questions": [{"name": "package", "instructions": "Package on the floor?"}],
            },
            blocking=True,
            return_response=True,
        )
    assert result["answers"] == {"package": {"type": "predicate", "probability": 0.92}}
    assert result["usage"] == {"input_tokens": 900}
    sent = aioclient_mock.mock_calls[-1][2]
    assert sent["model"] == "gpt-6-luna"
    assert sent["input"][0]["content"][1]["image_url"] == "data:image/jpeg;base64,/9g="
    assert sent["questions"] == [{"type": "predicate", "name": "package", "instructions": "Package on the floor?"}]
    assert aioclient_mock.mock_calls[-1][3]["Authorization"] == "Bearer sk-test"


async def test_decide_quota_error(hass: HomeAssistant, aioclient_mock, entry):
    aioclient_mock.post(
        DECISIONS,
        status=HTTPStatus.TOO_MANY_REQUESTS,
        json={"error": {"message": "You have no credits remaining."}},
    )
    with pytest.raises(HomeAssistantError, match="no credits"):
        await hass.services.async_call(
            DOMAIN,
            "decide",
            {"text": "hi", "questions": [{"name": "p", "instructions": "?"}]},
            blocking=True,
            return_response=True,
        )


async def test_decide_auth_error_starts_reauth(hass: HomeAssistant, aioclient_mock, entry):
    aioclient_mock.post(DECISIONS, status=HTTPStatus.UNAUTHORIZED, json={"error": {"message": "revoked"}})
    with pytest.raises(HomeAssistantError, match="revoked"):
        await hass.services.async_call(
            DOMAIN,
            "decide",
            {"text": "hi", "questions": [{"name": "p", "instructions": "?"}]},
            blocking=True,
            return_response=True,
        )
    await hass.async_block_till_done()
    assert any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())


async def test_decide_needs_input(hass: HomeAssistant, entry):
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "decide",
            {"questions": [{"name": "p", "instructions": "?"}]},
            blocking=True,
            return_response=True,
        )
