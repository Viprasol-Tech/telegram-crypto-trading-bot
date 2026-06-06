from __future__ import annotations

from typer.testing import CliRunner

from telegram_crypto_trading_bot import __version__
from telegram_crypto_trading_bot.cli import app

runner = CliRunner()


def test_version_subcommand() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_demo_subcommand_runs() -> None:
    result = runner.invoke(app, ["demo"])
    assert result.exit_code == 0
    assert "Final equity" in result.stdout
    assert "/portfolio" in result.stdout


def test_chat_subcommand_replays_messages() -> None:
    result = runner.invoke(app, ["chat", "-m", "/buy BTC 1", "-m", "/balance"])
    assert result.exit_code == 0
    assert "BOUGHT" in result.stdout


def test_risk_subcommand_lists_limits() -> None:
    result = runner.invoke(app, ["risk"])
    assert result.exit_code == 0
    assert "Max order notional" in result.stdout


def test_backtest_threshold() -> None:
    result = runner.invoke(app, ["backtest", "--strategy", "threshold"])
    assert result.exit_code == 0
    assert "Backtest" in result.stdout
    assert "Total PnL" in result.stdout


def test_backtest_sma() -> None:
    result = runner.invoke(app, ["backtest", "--strategy", "sma"])
    assert result.exit_code == 0
    assert "Signals" in result.stdout


def test_backtest_invalid_strategy() -> None:
    result = runner.invoke(app, ["backtest", "--strategy", "nope"])
    assert result.exit_code != 0
