"""SSRF guard tests for the agent HTTP tools (C10)."""

from __future__ import annotations

import pytest

from app.agents.tools.http_request import SSRFError, _validate_public_url, http_get


@pytest.mark.anyio
@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata (link-local)
        "http://127.0.0.1:8000/health",  # loopback
        "https://localhost/admin",  # resolves to loopback
        "http://10.1.2.3/internal",  # RFC-1918 private
        "http://192.168.0.1/",  # RFC-1918 private
        "http://172.16.5.5/",  # RFC-1918 private
        "ftp://example.com/file",  # disallowed scheme
        "file:///etc/passwd",  # disallowed scheme
    ],
)
async def test_validate_public_url_blocks_non_public_targets(url: str) -> None:
    with pytest.raises(SSRFError):
        await _validate_public_url(url)


@pytest.mark.anyio
async def test_validate_public_url_allows_public_ip() -> None:
    # A literal public IP passes (no DNS needed); raises nothing.
    await _validate_public_url("https://8.8.8.8/resolve")


@pytest.mark.anyio
async def test_http_get_blocks_metadata_without_network() -> None:
    result = await http_get("http://169.254.169.254/latest/meta-data/")
    assert result["ok"] is False
    assert result["status_code"] == 403
    assert "Blocked" in result["data"]
