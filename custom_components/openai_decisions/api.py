"""Thin async client for the OpenAI Decisions API."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .const import API_BASE


class DecisionsError(Exception):
    """Base error."""


class DecisionsAuthError(DecisionsError):
    """API key rejected."""


class DecisionsQuotaError(DecisionsError):
    """Out of credits or rate limited."""


class DecisionsClient:
    """Calls /v1/decisions with one API key."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    async def validate(self, timeout: float = 15) -> None:
        """Check the key with a free request (lists models)."""
        await self._request("GET", "/models", None, timeout)

    async def decide(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        """POST a decisions request and return the JSON body."""
        return await self._request("POST", "/decisions", payload, timeout)

    async def _request(
        self, method: str, path: str, payload: dict[str, Any] | None, timeout: float
    ) -> dict[str, Any]:
        try:
            async with self._session.request(
                method,
                f"{API_BASE}{path}",
                json=payload,
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                try:
                    body = await resp.json(content_type=None)
                except ValueError:
                    body = {}
                if resp.status < 400:
                    return body
                message = _error_message(body) or "no error message"
                if resp.status == 401:
                    raise DecisionsAuthError(message)
                if resp.status == 429:
                    raise DecisionsQuotaError(message)
                raise DecisionsError(f"HTTP {resp.status}: {message}")
        except asyncio.TimeoutError as err:
            raise DecisionsError(f"timed out after {timeout} s") from err
        except aiohttp.ClientError as err:
            raise DecisionsError(f"connection error: {err}") from err


def _error_message(body: Any) -> str | None:
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        return body["error"].get("message")
    return None
