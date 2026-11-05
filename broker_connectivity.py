"""Broker capability registry and fail-closed purchase routing.

Live trading requires a separately implemented and audited provider adapter.
No browser automation, credential scraping or unofficial endpoints are used.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


@dataclass(frozen=True)
class BrokerCapability:
    broker: str
    instruments: str
    api_status: Literal["documented", "not_publicly_verified"]
    live_purchase_enabled: bool
    integration_status: str
    documentation: str


CAPABILITIES = {
    "alpaca": BrokerCapability(
        "alpaca", "US equities and ETFs", "documented", False,
        "adapter_not_yet_implemented", "https://docs.alpaca.markets/"),
    "ibkr": BrokerCapability(
        "ibkr", "multi-asset, account dependent", "documented", False,
        "requires_authenticated_gateway_and_session", "https://www.interactivebrokers.com/docs/"),
    "webull": BrokerCapability(
        "webull", "US equities, ETFs and eligible instruments", "documented", False,
        "requires_official_sdk_and_approved_api_keys", "https://developer.webull.com/apis/docs/"),
    "webull_pay": BrokerCapability(
        "webull_pay", "crypto only", "documented", False,
        "requires_separate_crypto_api_keys_and_review", "https://act.webullpay.com/open-api"),
    "merrill": BrokerCapability(
        "merrill", "brokerage, manual order entry only", "not_publicly_verified", False,
        "no_verified_public_retail_order_api", "https://www.merrilledge.com/"),
}


def broker_capabilities() -> list[dict]:
    return [asdict(CAPABILITIES[key]) for key in sorted(CAPABILITIES)]


def route_purchase(broker: str, symbol: str, notional: float, *,
                   execute_live: bool = False) -> dict:
    """Generate a pending paper request or reject live execution.

    This interface is intentionally fail-closed until vetted adapters and
    explicit account-level approval controls have been implemented.
    """
    from purchase_now import prepare_purchase
    if broker not in CAPABILITIES:
        raise ValueError("unsupported broker")
    if execute_live:
        raise PermissionError(
            f"Live purchase for {broker} is disabled: "
            f"{CAPABILITIES[broker].integration_status}"
        )
    request = prepare_purchase(symbol, notional)
    request["broker"] = broker
    request["broker_integration_status"] = CAPABILITIES[broker].integration_status
    request["live_execution_available"] = False
    return request
