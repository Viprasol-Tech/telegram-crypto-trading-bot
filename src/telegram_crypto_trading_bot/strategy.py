"""A pluggable strategy runner for automated paper trading.

A :class:`Strategy` looks at the latest market snapshot plus the account and
returns zero or more :class:`Signal` objects. The :class:`StrategyRunner` feeds
each signal through the same risk checks and paper account the manual commands
use, so automated and manual flows share one execution path.

Two batteries-included strategies are provided:

* :class:`ThresholdStrategy` — buy below a floor, sell above a ceiling.
* :class:`SmaCrossStrategy` — trade on a fast/slow moving-average crossover.

Custom strategies only need to implement :meth:`Strategy.generate`.

Part of Telegram Crypto Trading Bot by Viprasol Tech Private Limited
(https://viprasol.com).
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from telegram_crypto_trading_bot.commands import Side, Trade
from telegram_crypto_trading_bot.paper import PaperAccount
from telegram_crypto_trading_bot.risk import RiskLimits, check_trade


@dataclass(frozen=True, slots=True)
class Signal:
    """A strategy's intent to trade.

    Args:
        side: Buy or sell.
        symbol: Upper-cased ticker.
        quantity: Units to trade (strictly positive).
        reason: Short human-readable rationale (shown in run reports).
    """

    side: Side
    symbol: str
    quantity: float
    reason: str = ""

    def as_trade(self) -> Trade:
        """Convert this signal into a parsed :class:`Trade` command."""
        return Trade(side=self.side, symbol=self.symbol, quantity=self.quantity)


@runtime_checkable
class Strategy(Protocol):
    """Anything that turns a market snapshot into trade signals."""

    name: str

    def generate(self, prices: Mapping[str, float], account: PaperAccount) -> list[Signal]:
        """Return signals for the given ``prices`` snapshot and ``account``."""
        ...


class ThresholdStrategy:
    """Buy when price dips below ``buy_below``; sell above ``sell_above``.

    A simple mean-reversion baseline: accumulate ``quantity`` units while the
    market is cheap and offload the position while it is rich.

    Args:
        symbol: Ticker to trade (case-insensitive).
        buy_below: Buy when the mark is at or under this price.
        sell_above: Sell when the mark is at or over this price.
        quantity: Units per signal (strictly positive).

    Raises:
        ValueError: If ``quantity`` is not positive or thresholds invert.
    """

    name = "threshold"

    def __init__(
        self,
        symbol: str,
        buy_below: float,
        sell_above: float,
        quantity: float,
    ) -> None:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if buy_below >= sell_above:
            raise ValueError("buy_below must be < sell_above")
        self.symbol = symbol.upper()
        self.buy_below = buy_below
        self.sell_above = sell_above
        self.quantity = quantity

    def generate(self, prices: Mapping[str, float], account: PaperAccount) -> list[Signal]:
        """Emit at most one buy or sell signal for the configured symbol."""
        price = prices.get(self.symbol)
        if price is None:
            return []
        if price <= self.buy_below:
            return [
                Signal(
                    Side.BUY,
                    self.symbol,
                    self.quantity,
                    reason=f"price {price:g} <= buy_below {self.buy_below:g}",
                )
            ]
        held = account.position(self.symbol)
        if price >= self.sell_above and held > 0:
            qty = min(self.quantity, held)
            return [
                Signal(
                    Side.SELL,
                    self.symbol,
                    qty,
                    reason=f"price {price:g} >= sell_above {self.sell_above:g}",
                )
            ]
        return []


class SmaCrossStrategy:
    """Trade on a fast/slow simple-moving-average crossover.

    Maintains a rolling price window per symbol. When the fast SMA crosses above
    the slow SMA it buys; when it crosses below and a position is held it sells.

    Args:
        symbol: Ticker to trade (case-insensitive).
        fast: Fast SMA window length (>= 1).
        slow: Slow SMA window length (> ``fast``).
        quantity: Units per signal (strictly positive).

    Raises:
        ValueError: If windows are invalid or ``quantity`` is not positive.
    """

    name = "sma_cross"

    def __init__(self, symbol: str, fast: int, slow: int, quantity: float) -> None:
        if fast < 1 or slow <= fast:
            raise ValueError("require 1 <= fast < slow")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        self.symbol = symbol.upper()
        self.fast = fast
        self.slow = slow
        self.quantity = quantity
        self._window: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=slow))
        self._prev_fast_above: dict[str, bool] = {}

    def generate(self, prices: Mapping[str, float], account: PaperAccount) -> list[Signal]:
        """Update the rolling window and emit a signal on a crossover."""
        price = prices.get(self.symbol)
        if price is None:
            return []
        window = self._window[self.symbol]
        window.append(price)
        if len(window) < self.slow:
            return []
        data = list(window)
        fast_sma = sum(data[-self.fast :]) / self.fast
        slow_sma = sum(data) / self.slow
        fast_above = fast_sma > slow_sma
        prev = self._prev_fast_above.get(self.symbol)
        self._prev_fast_above[self.symbol] = fast_above
        if prev is None or prev == fast_above:
            return []
        if fast_above:
            return [Signal(Side.BUY, self.symbol, self.quantity, reason="fast SMA crossed above")]
        held = account.position(self.symbol)
        if held > 0:
            qty = min(self.quantity, held)
            return [Signal(Side.SELL, self.symbol, qty, reason="fast SMA crossed below")]
        return []


@dataclass(frozen=True, slots=True)
class ExecutedSignal:
    """The result of running one :class:`Signal` through the runner.

    Args:
        signal: The originating signal.
        executed: Whether the trade actually filled.
        detail: Fill summary, or the rejection/error reason if not executed.
    """

    signal: Signal
    executed: bool
    detail: str


class StrategyRunner:
    """Drives a :class:`Strategy`, enforcing risk on every generated signal.

    Args:
        strategy: The strategy to run.
        account: The paper account signals execute against.
        limits: Risk policy applied to every buy signal. Defaults to unlimited.
    """

    def __init__(
        self,
        strategy: Strategy,
        account: PaperAccount,
        limits: RiskLimits | None = None,
    ) -> None:
        self.strategy = strategy
        self.account = account
        self.limits = limits or RiskLimits.unlimited()

    def step(self, prices: Mapping[str, float]) -> list[ExecutedSignal]:
        """Generate and attempt to execute signals for one price snapshot.

        Args:
            prices: Mapping of symbol -> mark price for this tick.

        Returns:
            One :class:`ExecutedSignal` per generated signal, in order.
        """
        results: list[ExecutedSignal] = []
        for signal in self.strategy.generate(prices, self.account):
            results.append(self._execute(signal, prices))
        return results

    def run(self, history: list[Mapping[str, float]]) -> list[ExecutedSignal]:
        """Replay a list of price snapshots, executing signals at each step.

        Args:
            history: Chronological list of price snapshots.

        Returns:
            The flattened list of executed signals across all steps.
        """
        out: list[ExecutedSignal] = []
        for snapshot in history:
            out.extend(self.step(snapshot))
        return out

    def _execute(self, signal: Signal, prices: Mapping[str, float]) -> ExecutedSignal:
        price = prices.get(signal.symbol)
        if price is None:
            return ExecutedSignal(signal, False, f"no price for {signal.symbol}")
        trade = signal.as_trade()
        decision = check_trade(trade, price, self.account, self.limits)
        if not decision.allowed:
            return ExecutedSignal(signal, False, f"risk: {decision.reason}")
        try:
            if signal.side is Side.BUY:
                cost = self.account.buy(signal.symbol, signal.quantity, price)
                detail = f"bought {signal.quantity:g} @ {price:.2f} (cost {cost:.2f})"
            else:
                proceeds = self.account.sell(signal.symbol, signal.quantity, price)
                detail = f"sold {signal.quantity:g} @ {price:.2f} (proceeds {proceeds:.2f})"
        except ValueError as exc:
            return ExecutedSignal(signal, False, f"error: {exc}")
        return ExecutedSignal(signal, True, detail)
