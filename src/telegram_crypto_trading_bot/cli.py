"""Command-line interface for Telegram Crypto Trading Bot.

Subcommands:

* ``version``   — print the installed version.
* ``demo``      — feed sample Telegram commands through the dispatcher.
* ``chat``      — replay one or more ``--message`` commands interactively.
* ``backtest``  — run a built-in strategy over a synthetic price path.
* ``risk``      — print the default risk policy.

Everything runs against an in-memory transport and a paper account — no token,
no API keys, no risk.

Part of Telegram Crypto Trading Bot by Viprasol Tech Private Limited
(https://viprasol.com).
"""

from __future__ import annotations

from collections.abc import Mapping

import typer
from rich.console import Console
from rich.table import Table

from telegram_crypto_trading_bot import __version__
from telegram_crypto_trading_bot.bot import (
    Dispatcher,
    InMemoryTransport,
    StaticPriceSource,
    run_once,
)
from telegram_crypto_trading_bot.paper import PaperAccount, build_portfolio
from telegram_crypto_trading_bot.risk import RiskLimits
from telegram_crypto_trading_bot.strategy import (
    SmaCrossStrategy,
    Strategy,
    StrategyRunner,
    ThresholdStrategy,
)

app = typer.Typer(add_completion=False, help="Telegram Crypto Trading Bot — by Viprasol Tech.")
console = Console()

_DEMO_COMMANDS = [
    "/help",
    "/price BTC",
    "/buy BTC 0.5",
    "/buy ETH 2",
    "/positions",
    "/sell BTC 0.2",
    "/pnl",
    "/portfolio",
    "/history 3",
    "/risk",
    "/buy BTC 100",
]

_DEMO_PRICES = {"BTC": 30_000.0, "ETH": 2_000.0, "DOGE": 0.15}


def _demo_limits() -> RiskLimits:
    return RiskLimits(max_order_notional=1_000_000.0, max_open_positions=5)


@app.command()
def version() -> None:
    """Print the installed version."""
    console.print(f"telegram-crypto-trading-bot [bold cyan]{__version__}[/] — by Viprasol Tech")


@app.command()
def demo() -> None:
    """Feed sample Telegram commands through the bot and print replies."""
    prices = StaticPriceSource(_DEMO_PRICES)
    account = PaperAccount(cash=100_000.0)
    dispatcher = Dispatcher(account, prices, limits=_demo_limits())
    transport = InMemoryTransport(inbound=list(_DEMO_COMMANDS))

    replies = run_once(dispatcher, transport)
    for command, reply in zip(_DEMO_COMMANDS, replies, strict=True):
        head, _, _ = reply.partition("\n")
        suffix = " ..." if "\n" in reply else ""
        console.print(f"[bold cyan]{command:<14}[/] -> {head}{suffix}")

    portfolio = build_portfolio(account, _DEMO_PRICES)
    console.print(
        f"\nFinal equity: [bold green]${portfolio.equity:,.2f}[/] "
        f"(started $100,000.00, total PnL {portfolio.total_pnl:+,.2f})"
    )


@app.command()
def chat(
    message: list[str] = typer.Option(
        ...,
        "--message",
        "-m",
        help="A command to send (repeatable), e.g. -m '/buy BTC 1'.",
    ),
) -> None:
    """Replay one or more ``--message`` commands and print each reply."""
    prices = StaticPriceSource(_DEMO_PRICES)
    account = PaperAccount(cash=100_000.0)
    dispatcher = Dispatcher(account, prices, limits=_demo_limits())
    for text in message:
        reply = dispatcher.handle_text(text)
        console.print(f"[bold cyan]{text}[/]")
        console.print(reply)


@app.command()
def backtest(
    strategy: str = typer.Option("threshold", help="Strategy: 'threshold' or 'sma'."),
    symbol: str = typer.Option("BTC", help="Symbol to trade."),
    cash: float = typer.Option(50_000.0, help="Starting cash."),
) -> None:
    """Run a built-in strategy over a synthetic price path and show results."""
    path = [100.0, 96.0, 92.0, 95.0, 105.0, 112.0, 108.0, 90.0, 88.0, 115.0]
    history: list[Mapping[str, float]] = [{symbol.upper(): p} for p in path]

    strat: Strategy
    if strategy == "sma":
        strat = SmaCrossStrategy(symbol, fast=2, slow=4, quantity=1.0)
    elif strategy == "threshold":
        strat = ThresholdStrategy(symbol, buy_below=95.0, sell_above=110.0, quantity=1.0)
    else:
        raise typer.BadParameter("strategy must be 'threshold' or 'sma'")

    account = PaperAccount(cash=cash)
    runner = StrategyRunner(strat, account, limits=RiskLimits(max_order_notional=10_000.0))
    results = runner.run(history)

    table = Table(title=f"Backtest: {strat.name} on {symbol.upper()}")
    table.add_column("Signal", style="cyan")
    table.add_column("Filled")
    table.add_column("Detail")
    executed = 0
    for res in results:
        executed += int(res.executed)
        table.add_row(
            f"{res.signal.side.value} {res.signal.quantity:g}",
            "yes" if res.executed else "no",
            res.detail,
        )
    if not results:
        table.add_row("-", "-", "no signals generated")
    console.print(table)

    final = path[-1]
    portfolio = build_portfolio(account, {symbol.upper(): final})
    console.print(
        f"Signals: {len(results)} ({executed} filled) | "
        f"Equity: [bold green]${portfolio.equity:,.2f}[/] | "
        f"Total PnL: {portfolio.total_pnl:+,.2f}"
    )


@app.command()
def risk() -> None:
    """Print the default demo risk policy."""
    for line in _demo_limits().describe():
        console.print(f"- {line}")


if __name__ == "__main__":
    app()
