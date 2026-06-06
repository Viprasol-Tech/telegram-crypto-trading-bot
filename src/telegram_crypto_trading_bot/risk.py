"""Pre-trade risk limits and their enforcement.

:class:`RiskLimits` is a declarative, validated policy. :func:`check_trade`
evaluates a proposed buy/sell against the policy *before* it touches the
account, returning a :class:`RiskDecision`. Rejections are explicit and
human-readable so the bot can refuse an order and explain why.

Enforced rules:

* **Max notional per order** — cap the value of any single fill.
* **Max position notional** — cap total exposure to one symbol.
* **Max open positions** — cap how many distinct symbols may be held.
* **Min cash reserve** — never let a buy drop cash below a floor.

Part of Telegram Crypto Trading Bot by Viprasol Tech Private Limited
(https://viprasol.com).
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from telegram_crypto_trading_bot.commands import Side, Trade
from telegram_crypto_trading_bot.paper import PaperAccount


class RiskError(ValueError):
    """Raised when a trade is rejected by the active risk policy."""


class RiskLimits(BaseModel):
    """A declarative pre-trade risk policy.

    All limits are optional; ``None`` disables that particular check. Values are
    validated on construction so an impossible policy fails fast.

    Args:
        max_order_notional: Max value (price * qty) of any single order.
        max_position_notional: Max total value held in any single symbol.
        max_open_positions: Max number of distinct symbols held at once.
        min_cash_reserve: Cash floor a buy may not breach.
    """

    model_config = ConfigDict(frozen=True)

    max_order_notional: float | None = Field(default=None, gt=0)
    max_position_notional: float | None = Field(default=None, gt=0)
    max_open_positions: int | None = Field(default=None, gt=0)
    min_cash_reserve: float | None = Field(default=None, ge=0)

    @classmethod
    def unlimited(cls) -> RiskLimits:
        """Return a policy that imposes no limits at all."""
        return cls()

    def describe(self) -> list[str]:
        """Return human-readable lines describing each configured limit."""
        lines: list[str] = []
        if self.max_order_notional is not None:
            lines.append(f"Max order notional: {self.max_order_notional:,.2f}")
        if self.max_position_notional is not None:
            lines.append(f"Max position notional: {self.max_position_notional:,.2f}")
        if self.max_open_positions is not None:
            lines.append(f"Max open positions: {self.max_open_positions}")
        if self.min_cash_reserve is not None:
            lines.append(f"Min cash reserve: {self.min_cash_reserve:,.2f}")
        if not lines:
            lines.append("No risk limits configured (unlimited).")
        return lines


@dataclass(frozen=True, slots=True)
class RiskDecision:
    """The outcome of a pre-trade risk check.

    Args:
        allowed: Whether the trade may proceed.
        reason: Explanation of a rejection (empty when ``allowed`` is True).
    """

    allowed: bool
    reason: str = ""

    @classmethod
    def ok(cls) -> RiskDecision:
        """Return an approving decision."""
        return cls(allowed=True)

    @classmethod
    def reject(cls, reason: str) -> RiskDecision:
        """Return a rejecting decision carrying ``reason``."""
        return cls(allowed=False, reason=reason)


def check_trade(
    trade: Trade,
    price: float,
    account: PaperAccount,
    limits: RiskLimits,
) -> RiskDecision:
    """Evaluate ``trade`` at ``price`` against ``limits`` for ``account``.

    Sells are always allowed (they reduce exposure); only buys are gated.

    Args:
        trade: The proposed order.
        price: The fill price the order would execute at.
        account: The account the order would touch (read-only here).
        limits: The active risk policy.

    Returns:
        A :class:`RiskDecision`. ``allowed`` is False with a ``reason`` when a
        limit would be breached.
    """
    if trade.side is Side.SELL:
        return RiskDecision.ok()

    notional = trade.quantity * price

    if limits.max_order_notional is not None and notional > limits.max_order_notional:
        return RiskDecision.reject(
            f"order notional {notional:,.2f} exceeds limit {limits.max_order_notional:,.2f}"
        )

    if limits.max_position_notional is not None:
        existing = account.position(trade.symbol) * price
        if existing + notional > limits.max_position_notional:
            return RiskDecision.reject(
                f"position notional {existing + notional:,.2f} for {trade.symbol} "
                f"exceeds limit {limits.max_position_notional:,.2f}"
            )

    if limits.max_open_positions is not None:
        is_new_symbol = account.position(trade.symbol) == 0.0
        if is_new_symbol and len(account.positions) >= limits.max_open_positions:
            return RiskDecision.reject(
                f"opening {trade.symbol} would exceed max open positions "
                f"({limits.max_open_positions})"
            )

    if limits.min_cash_reserve is not None:
        cash_after = account.cash - notional
        if cash_after < limits.min_cash_reserve:
            return RiskDecision.reject(
                f"cash after trade {cash_after:,.2f} below reserve {limits.min_cash_reserve:,.2f}"
            )

    return RiskDecision.ok()
