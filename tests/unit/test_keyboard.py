from __future__ import annotations

import pytest

from telegram_crypto_trading_bot.keyboard import (
    Button,
    InlineKeyboard,
    callback_text,
    confirm,
    main_menu,
    quick_trade,
)


def test_button_callback_data_is_namespaced() -> None:
    btn = Button("Balance", "balance")
    assert btn.callback_data == "cmd:balance"


def test_callback_text_maps_back_to_command() -> None:
    assert callback_text("cmd:balance") == "/balance"
    assert callback_text("cmd:buy BTC 1") == "/buy BTC 1"


def test_callback_text_rejects_unknown_prefix() -> None:
    with pytest.raises(ValueError):
        callback_text("garbage")


def test_callback_text_rejects_empty_action() -> None:
    with pytest.raises(ValueError):
        callback_text("cmd:   ")


def test_button_roundtrips_through_callback() -> None:
    btn = Button("Buy", "buy BTC 0.1")
    assert callback_text(btn.callback_data) == "/buy BTC 0.1"


def test_inline_keyboard_to_telegram_shape() -> None:
    kb = InlineKeyboard(rows=[[Button("A", "balance"), Button("B", "pnl")]])
    payload = kb.to_telegram()
    assert payload == {
        "inline_keyboard": [
            [
                {"text": "A", "callback_data": "cmd:balance"},
                {"text": "B", "callback_data": "cmd:pnl"},
            ]
        ]
    }


def test_main_menu_has_expected_actions() -> None:
    actions = {btn.action for btn in main_menu().buttons()}
    assert {"balance", "positions", "portfolio", "pnl", "history", "risk"} <= actions


def test_quick_trade_builds_buy_and_sell() -> None:
    kb = quick_trade("btc", 0.5)
    actions = [btn.action for btn in kb.buttons()]
    assert "buy BTC 0.5" in actions
    assert "sell BTC 0.5" in actions


def test_confirm_has_confirm_and_cancel() -> None:
    kb = confirm("sell BTC 1")
    actions = [btn.action for btn in kb.buttons()]
    assert actions == ["sell BTC 1", "balance"]
