"""An abstracted inline-keyboard action interface.

Telegram bots attach inline keyboards (grids of buttons) to messages; tapping a
button fires a *callback* carrying an opaque payload. This module models that
interaction transport-agnostically so it can be rendered to a real Telegram
``reply_markup`` or exercised in tests without a network.

* :class:`Button` / :class:`InlineKeyboard` describe the layout.
* :func:`callback_text` maps a tapped button's payload back to a bot command.
* Helpers build common keyboards (a main menu, a confirm dialog, quick-trade
  shortcuts) so callers do not hand-assemble button grids.

Part of Telegram Crypto Trading Bot by Viprasol Tech Private Limited
(https://viprasol.com).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from telegram_crypto_trading_bot.commands import Side

# Callback payloads are namespaced ``cmd:...`` so a tap maps cleanly to a command.
_PREFIX = "cmd:"


@dataclass(frozen=True, slots=True)
class Button:
    """A single inline-keyboard button.

    Args:
        label: The text shown on the button.
        action: The bot command the button triggers, e.g. ``"balance"`` or
            ``"buy BTC 0.1"``. Stored verbatim; rendered into a namespaced
            ``callback_data`` payload.
    """

    label: str
    action: str

    @property
    def callback_data(self) -> str:
        """The opaque payload sent when this button is tapped."""
        return f"{_PREFIX}{self.action}"


@dataclass(frozen=True, slots=True)
class InlineKeyboard:
    """A grid of :class:`Button` rows.

    Args:
        rows: A list of button rows; each row is a list of :class:`Button`.
    """

    rows: list[list[Button]] = field(default_factory=list)

    def to_telegram(self) -> dict[str, list[list[dict[str, str]]]]:
        """Render to a Telegram ``inline_keyboard`` ``reply_markup`` dict.

        Returns:
            A dict suitable for ``reply_markup`` in a ``sendMessage`` call.
        """
        return {
            "inline_keyboard": [
                [{"text": btn.label, "callback_data": btn.callback_data} for btn in row]
                for row in self.rows
            ]
        }

    def buttons(self) -> list[Button]:
        """Return all buttons flattened across rows, top-to-bottom."""
        return [btn for row in self.rows for btn in row]


def callback_text(callback_data: str) -> str:
    """Translate a tapped button's payload back into a bot command string.

    Args:
        callback_data: The opaque payload Telegram delivers on a tap.

    Returns:
        The command text (e.g. ``"/balance"``), ready to feed to the dispatcher.

    Raises:
        ValueError: If ``callback_data`` is not a recognised namespaced payload.
    """
    if not callback_data.startswith(_PREFIX):
        raise ValueError(f"unrecognised callback payload: {callback_data!r}")
    action = callback_data[len(_PREFIX) :].strip()
    if not action:
        raise ValueError("empty callback action")
    return f"/{action}"


def main_menu() -> InlineKeyboard:
    """Build the default action menu shown on ``/help`` and ``/start``."""
    return InlineKeyboard(
        rows=[
            [Button("Balance", "balance"), Button("Positions", "positions")],
            [Button("Portfolio", "portfolio"), Button("PnL", "pnl")],
            [Button("History", "history"), Button("Risk", "risk")],
        ]
    )


def quick_trade(symbol: str, quantity: float) -> InlineKeyboard:
    """Build a two-button buy/sell shortcut for ``symbol`` at ``quantity``.

    Args:
        symbol: Ticker to trade (upper-cased in labels and actions).
        quantity: Units each button trades.

    Returns:
        An :class:`InlineKeyboard` with a buy and a sell button.
    """
    sym = symbol.upper()
    return InlineKeyboard(
        rows=[
            [
                Button(f"Buy {quantity:g} {sym}", f"{Side.BUY.value} {sym} {quantity:g}"),
                Button(f"Sell {quantity:g} {sym}", f"{Side.SELL.value} {sym} {quantity:g}"),
            ]
        ]
    )


def confirm(action: str) -> InlineKeyboard:
    """Build a confirm/cancel dialog for ``action``.

    Args:
        action: The command to run if confirmed (e.g. ``"sell BTC 1"``).

    Returns:
        An :class:`InlineKeyboard` with a confirm button (running ``action``)
        and a cancel button (mapping to ``/balance`` as a safe no-op).
    """
    return InlineKeyboard(rows=[[Button("Confirm", action), Button("Cancel", "balance")]])
