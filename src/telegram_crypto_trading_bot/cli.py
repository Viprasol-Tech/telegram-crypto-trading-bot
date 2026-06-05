"""Command-line interface for Telegram Crypto Trading Bot.

``telegram-crypto-trading-bot demo`` feeds a few Telegram-style commands through
the dispatcher against an in-memory transport and a paper account, printing the
bot's replies — no token, no API keys, no risk.

Part of Telegram Crypto Trading Bot by Viprasol Tech Private Limited
(https://viprasol.com).
"""

from __future__ import annotations

import typer
from rich.console import Console

from telegram_crypto_trading_bot import __version__
from telegram_crypto_trading_bot.bot import (
    Dispatcher,
    InMemoryTransport,
    StaticPriceSource,
    run_once,
)
from telegram_crypto_trading_bot.paper import PaperAccount

app = typer.Typer(add_completion=False, help="Telegram Crypto Trading Bot — by Viprasol Tech.")
console = Console()

_DEMO_COMMANDS = [
    "/price BTC",
    "/balance",
    "/buy BTC 0.5",
    "/balance",
    "/sell BTC 0.2",
    "/balance",
    "/buy DOGE 100",
    "/sell BTC 999",
]


@app.command()
def version() -> None:
    """Print the installed version."""
    console.print(f"telegram-crypto-trading-bot [bold cyan]{__version__}[/] — by Viprasol Tech")


@app.command()
def demo() -> None:
    """Feed sample Telegram commands through the bot and print replies."""
    prices = StaticPriceSource({"BTC": 30_000.0, "DOGE": 0.15})
    account = PaperAccount(cash=20_000.0)
    dispatcher = Dispatcher(account, prices)
    transport = InMemoryTransport(inbound=list(_DEMO_COMMANDS))

    replies = run_once(dispatcher, transport)
    for command, reply in zip(_DEMO_COMMANDS, replies, strict=True):
        console.print(f"[bold cyan]{command:<14}[/] -> {reply}")

    console.print(
        f"\nFinal equity: [bold green]"
        f"${account.equity({'BTC': 30_000.0, 'DOGE': 0.15}):,.2f}[/] (started $20,000.00)"
    )


if __name__ == "__main__":
    app()
