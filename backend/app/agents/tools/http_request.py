"""HTTP Request tool — lets agents call external APIs (e.g. CoinGecko, Binance)."""

import asyncio
import ipaddress
import logging
from typing import Any
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30
_ALLOWED_SCHEMES = frozenset({"http", "https"})


class SSRFError(ValueError):
    """Raised when a requested URL targets a disallowed scheme or non-public address."""


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Block addresses an agent must never reach (cloud metadata, internal services)."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local  # 169.254.0.0/16 — includes 169.254.169.254 cloud metadata
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def _validate_public_url(url: str) -> None:
    """Reject non-http(s) schemes and any host that resolves to a non-public address.

    Guards against SSRF — without this an injected agent could hit the cloud metadata
    endpoint (→ IAM creds), localhost admin ports, or internal RFC-1918 services.
    """
    parts = urlsplit(url)
    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        raise SSRFError(f"Disallowed URL scheme '{parts.scheme}' (only http/https permitted)")
    host = parts.hostname
    if not host:
        raise SSRFError("URL has no host")

    # A literal IP in the URL must itself be public.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and _ip_is_blocked(literal):
        raise SSRFError(f"URL host {host} resolves to a non-public address")

    # Resolve the hostname; every resolved address must be public (defends against DNS
    # rebinding to internal ranges and hostnames that alias localhost/metadata).
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, parts.port or None)
    except OSError as exc:
        raise SSRFError(f"Could not resolve host {host}: {exc}") from exc
    for info in infos:
        addr = info[4][0]
        try:
            resolved = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _ip_is_blocked(resolved):
            raise SSRFError(f"URL host {host} resolves to a non-public address ({addr})")


async def http_get(
    url: str,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Perform an HTTP GET request and return the parsed JSON response.

    Returns a dict with keys: status_code (int), data (parsed JSON or text string), ok (bool).
    """
    try:
        await _validate_public_url(url)
    except SSRFError as exc:
        logger.warning("Blocked HTTP GET to %s: %s", url, exc)
        return {"status_code": 403, "data": f"Blocked: {exc}", "ok": False}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
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
    try:
        await _validate_public_url(url)
    except SSRFError as exc:
        logger.warning("Blocked HTTP POST to %s: %s", url, exc)
        return {"status_code": 403, "data": f"Blocked: {exc}", "ok": False}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
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
