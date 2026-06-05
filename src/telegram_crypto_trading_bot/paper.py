"""A minimal paper-trading account: cash, positions, and buy/sell fills.

No real exchange, no real money — every fill executes against a price you
supply, so the bot can be exercised end-to-end without API keys or risk.

Part of Telegram Crypto Trading Bot by Viprasol Tech Private Limited
(https://viprasol.com).
"""

from __future__ import annotations


class InsufficientFundsError(ValueError):
    """Raised when a buy would cost more cash than the account holds."""


class InsufficientPositionError(ValueError):
    """Raised when a sell exceeds the quantity currently held."""


class PaperAccount:
    """A simulated cash + spot account.

    Args:
        cash: Starting quote-currency balance (e.g. USD). Must be non-negative.

    Raises:
        ValueError: If ``cash`` is negative.
    """

    def __init__(self, cash: float = 10_000.0) -> None:
        if cash < 0:
            raise ValueError("starting cash must be non-negative")
        self._cash: float = float(cash)
        self._positions: dict[str, float] = {}

    @property
    def cash(self) -> float:
        """Current free quote-currency balance."""
        return self._cash

    @property
    def positions(self) -> dict[str, float]:
        """A copy of held positions, mapping symbol -> quantity."""
        return dict(self._positions)

    def position(self, symbol: str) -> float:
        """Return the quantity held for ``symbol`` (0.0 if none)."""
        return self._positions.get(symbol.upper(), 0.0)

    def buy(self, symbol: str, quantity: float, price: float) -> float:
        """Buy ``quantity`` of ``symbol`` at ``price``, paying from cash.

        Args:
            symbol: Ticker to buy (case-insensitive).
            quantity: Units to buy; must be strictly positive.
            price: Per-unit price; must be strictly positive.

        Returns:
            The total cost debited from cash.

        Raises:
            ValueError: If ``quantity`` or ``price`` is not positive.
            InsufficientFundsError: If the cost exceeds available cash.
        """
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if price <= 0:
            raise ValueError("price must be positive")
        cost = quantity * price
        if cost > self._cash:
            raise InsufficientFundsError(f"need {cost:.2f} but only {self._cash:.2f} available")
        key = symbol.upper()
        self._cash -= cost
        self._positions[key] = self._positions.get(key, 0.0) + quantity
        return cost

    def sell(self, symbol: str, quantity: float, price: float) -> float:
        """Sell ``quantity`` of ``symbol`` at ``price``, crediting cash.

        Args:
            symbol: Ticker to sell (case-insensitive).
            quantity: Units to sell; must be strictly positive.
            price: Per-unit price; must be strictly positive.

        Returns:
            The total proceeds credited to cash.

        Raises:
            ValueError: If ``quantity`` or ``price`` is not positive.
            InsufficientPositionError: If ``quantity`` exceeds the held amount.
        """
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if price <= 0:
            raise ValueError("price must be positive")
        key = symbol.upper()
        held = self._positions.get(key, 0.0)
        if quantity > held:
            raise InsufficientPositionError(f"holding {held} {key} but tried to sell {quantity}")
        proceeds = quantity * price
        self._cash += proceeds
        remaining = held - quantity
        if remaining > 0:
            self._positions[key] = remaining
        else:
            self._positions.pop(key, None)
        return proceeds

    def equity(self, prices: dict[str, float]) -> float:
        """Total account value: cash plus positions marked at ``prices``.

        Args:
            prices: Mapping of symbol -> mark price. Symbols absent from the
                mapping are valued at zero.

        Returns:
            Cash plus the sum of ``quantity * price`` over all positions.
        """
        marked = sum(qty * prices.get(sym, 0.0) for sym, qty in self._positions.items())
        return self._cash + marked
