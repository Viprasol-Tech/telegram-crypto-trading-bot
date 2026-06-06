# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[SemVer](https://semver.org/).

## [0.2.0] - 2025

### Added
- New commands: `/positions`, `/portfolio`, `/pnl`, `/history [N]`, `/risk`,
  and `/help` (with `/start`, `/pos`, `/port` aliases).
- Cost-basis accounting in `PaperAccount`: average entry price per symbol,
  realized PnL on sells, and mark-to-market unrealized PnL.
- An immutable `Fill` ledger recording every paper trade, powering `/history`.
- `Portfolio` / `PortfolioRow` snapshots via `build_portfolio()` with equity,
  realized/unrealized PnL, and total-return percentage.
- `risk` module: declarative, validated `RiskLimits` (max order notional, max
  position notional, max open positions, min cash reserve) enforced pre-trade
  by `check_trade()`; the dispatcher now rejects breaching buys with a reason.
- `strategy` module: a pluggable `Strategy` protocol, a `StrategyRunner` that
  routes every signal through the same risk + account path, and two built-in
  strategies (`ThresholdStrategy`, `SmaCrossStrategy`).
- `keyboard` module: a transport-agnostic inline-keyboard interface (`Button`,
  `InlineKeyboard`, `main_menu()`, `quick_trade()`, `confirm()`) plus
  `Dispatcher.handle_callback()` to map button taps back to commands.
- CLI subcommands: `chat`, `backtest`, and `risk` alongside `demo`/`version`.

### Changed
- `Dispatcher` now accepts an optional `RiskLimits` policy.
- The `demo` subcommand showcases the full command surface and risk rejection.

## [0.1.0] - 2025

### Added
- Initial release of telegram-crypto-trading-bot: Telegram-controlled crypto trading bot (command parser + paper trading).
