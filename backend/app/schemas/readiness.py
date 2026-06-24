"""Read-only trading readiness response schema.

Describes "what will the next order actually do" without ever exposing credential
values. ``credential_values_exposed`` is always ``False`` by construction.
"""

from __future__ import annotations

from app.schemas.base import BaseSchema


class TradingReadiness(BaseSchema):
    """Fail-closed, read-only view of the configured execution path.

    Never places an order and never mutates any env/setting. Only env var
    names/patterns are surfaced (``credentials_source``) — never values.
    """

    trading_mode: str
    exchange_mode: str
    market_type: str
    is_paper: bool
    is_demo: bool
    is_testnet: bool
    is_live: bool
    is_order_capable: bool
    live_trading_enabled: bool
    will_send_exchange_order: bool
    order_destination: str
    base_url_label: str
    credentials_configured: bool
    credentials_source: str
    credential_values_exposed: bool
    mode_conflict: bool
    readiness: str  # "ready" | "not_ready" | "conflict"
    blocking_reasons: list[str]
    warnings: list[str]
