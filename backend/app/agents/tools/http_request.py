"""HTTP Request tool — lets agents call external APIs (e.g. CoinGecko, Binance)."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30


async def http_get(
    url: str,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Perform an HTTP GET request and return the parsed JSON response.

    Returns a dict with keys: status_code (int), data (parsed JSON or text string), ok (bool).
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.get(url, headers=headers or {}, params=params or {})
            ok = resp.status_code < 400
            try:
                data: Any = resp.json()
            except Exception:
                data = resp.text
            logger.info("HTTP GET %s → %s", url, resp.status_code)
            return {"status_code": resp.status_code, "data": data, "ok": ok}
        except httpx.TimeoutException:
            return {"status_code": 408, "data": "Request timed out", "ok": False}
        except Exception as exc:
            return {"status_code": 500, "data": str(exc), "ok": False}


async def http_post(
    url: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Perform an HTTP POST request with a JSON body."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(url, json=body or {}, headers=headers or {})
            ok = resp.status_code < 400
            try:
                data: Any = resp.json()
            except Exception:
                data = resp.text
            logger.info("HTTP POST %s → %s", url, resp.status_code)
            return {"status_code": resp.status_code, "data": data, "ok": ok}
        except httpx.TimeoutException:
            return {"status_code": 408, "data": "Request timed out", "ok": False}
        except Exception as exc:
            return {"status_code": 500, "data": str(exc), "ok": False}
