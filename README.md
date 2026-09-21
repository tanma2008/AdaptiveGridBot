# AdaptiveGridBot

**AdaptiveGridBot** is an experimental algorithmic grid trading framework developed for research, strategy testing, and multi-generation backtesting. The repository contains core execution engines, risk management modules, real-time web monitoring dashboards, and a wide collection of historical backtesting and paper-trading experiment scripts.

---

## Features

- **Adaptive Grid Trading Engine**: Dynamically calculates and adjusts grid spacing, order boundaries, and position levels based on market volatility and indicators.
- **Market Data Handling**: Historical market data fetching, OHLCV candle processing, indicator calculation, and live price streaming.
- **Grid Engine & Order Management**: State-driven grid order placement, cancellation tracking, fill detection, and execution logic.
- **Risk Management System**: Drawdown monitoring, position limits, exposure cap verification, and stop-loss mechanisms.
- **Account & Portfolio Tracking**: Balance monitoring, margin checking, and portfolio tracking across active pairs.
- **Real-Time Web Dashboard**: Built-in interactive HTTP dashboard (`adaptive_grid_dashboard.py`) for live monitoring of active grids, open orders, equity, and performance telemetry.
- **Comprehensive Backtesting Suite**: Supports historical backtests, realized PnL analysis, edge validation, walk-forward testing, and candidate parameter optimization.
- **Demo / Paper-Trading Workflows**: Isolated demo loops and paper-trading runners for dry-running strategies safely.

---

## Architecture

The system is structured around modular components responsible for distinct execution layers:

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│   Market Data   │ ──► │ Indicators / Strategy│ ──► │   Grid Engine   │
└─────────────────┘     └──────────────────────┘     └─────────────────┘
                                                              │
┌─────────────────┐     ┌──────────────────────┐              ▼
│    Dashboard /  │ ◄── │    Exchange / Demo   │ ◄── ┌─────────────────┐
│   Monitoring    │     │   (Execution Layer)  │     │   Risk Engine   │
└─────────────────┘     └──────────────────────┘     └─────────────────┘
                                  ▲                           │
                                  └──── ┌─────────────────┐ ──┘
                                        │  Order Manager  │
                                        └─────────────────┘
```

### Core Modules

- **`market_data.py`**: Handles price feed ingestion, historical data loading, and technical analysis helpers.
- **`grid_engine.py`**: Core mathematical model for grid level generation, dynamic spacing adjustment, and order matrix construction.
- **`order_manager.py`**: Coordinates order submission, status polling, fill reconciliation, and cancellation logic.
- **`risk_engine.py`**: Enforces strict safety rules, maximum exposure limits, drawdown thresholds, and emergency halts.
- **`account_manager.py`**: Tracks account balances, margin health, and position statistics.
- **`adaptive_grid_dashboard.py`**: Single-file web interface providing visual telemetry, active grid monitoring, and performance charts.

---

## Strategy Versions

The repository documents the evolution of the Adaptive Grid strategy across several experimental generations:

- **Early Experiments (`v0.1` – `v0.4`)**: Initial grid engine prototypes, simple fixed-spacing models, and baseline backtesting setups (e.g., `grid_bot_v02.py`, `adaptive_grid_v04.py`).
- **Generation 4.8 (`v0.4.8` / `v4.8`)**: Introduced smart loop execution, risk-capped position sizing, and realized PnL tracking (e.g., `adaptive_grid_v048_demo_smart_loop.py`, `eth_grid_engine_v048.py`).
- **Generation 4.9 (`v0.4.9` / `v4.9`)**: Multi-asset adaptations, refined cadence controls, and updated order managers (e.g., `adaptive_grid_v049_boss_demo_smart_loop.py`, `sol_order_manager_v049.py`).
- **Generation 5.0 (`v0.5.0` / `v5.0`)**: Enhanced candidate filtering, walk-forward validation models, and persistent grid state tracking (e.g., `adaptive_grid_v050_demo_smart_loop.py`).
- **Generation 5.1 (`v0.5.1` / `v0.5.1.1`)**: Full persistent grid implementation, fill simulation tools, and multi-walkforward optimization scripts (e.g., `adaptive_grid_v0511_demo_smart_loop_FULL.py`).

*Note: The repository contains multiple experimental variants and demo scripts representing different development stages. No single version is designated as universally superior.*

---

## Supported / Tested Markets

The codebase includes specific configurations, backtest scripts, and demo bot variants tailored for:

- **Bitcoin (BTC)**: e.g., `adaptive_grid_bot_A_btc.py`, `adaptive_grid_bot_B_btc.py`, `adaptive_grid_bot_C_btc.py`
- **Ethereum (ETH)**: e.g., `adaptive_grid_bot_D_eth.py`, `eth_adaptive_grid_v049_demo_smart_loop.py`, `eth_backtest_v048.py`
- **Solana (SOL)**: e.g., `adaptive_grid_bot_G_sol.py`, `sol_adaptive_grid_v049_demo_smart_loop.py`, `adaptive_grid_v048_sol_G_demo_smart_loop.py`

---

## Backtesting & Analysis Suite

A significant part of this repository consists of backtesting and analytical utilities:

- **`backtest_v048_realized_pnl.py`**: Evaluates realized PnL distributions and grid fill efficiency.
- **`backtest_v047_edge_analysis.py`**: Performs statistical edge verification across volatile market regimes.
- **`backtest_v050_multi_walkforward.py`**: Multi-window walk-forward testing to detect curve-fitting.
- **`backtest_v05_30d_optimizer_DOWNLOAD.py`**: Automated parameter optimization across historical market windows.
- **`eth_backtest_validate_v049.py`**: Out-of-sample validation runner for Ethereum grid configurations.
- **`backtest_v045_riskcap.py`**: Risk-capped exposure and drawdown stress-testing module.

---

## Dashboard & Monitoring

The repository includes `adaptive_grid_dashboard.py`, a lightweight web dashboard that serves a real-time monitoring panel. It provides:

- Live grid state visualization (upper/lower bounds, active grid lines, current index).
- Open orders table and fill history reconciliation.
- Account equity curve, unrealized/realized PnL breakdown.
- System health, API latency telemetry, and log streaming.

Auxiliary reporting scripts such as `okx_demo_report_v05.py` and `backtest_report.py` provide additional summary generation.

---

## Getting Started

### Prerequisites & Installation

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/tanma2008/AdaptiveGridBot.git
   cd AdaptiveGridBot
   ```

2. **Set Up a Virtual Environment**:
   - **Windows**:
     ```cmd
     python -m venv .venv
     .venv\Scripts\activate
     ```
   - **Linux / macOS**:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. **Install Dependencies**:
   If a specific requirements file is present for your target script (e.g., `requirements_v048.txt`), install via:
   ```bash
   pip install -r requirements_v048.txt
   ```
   *Standard dependencies typically include `requests`, `pandas`, `numpy`, and market data / exchange API client libraries.*

---

## Configuration & Security

- **API Credentials**: Never hardcode API keys, secret keys, or passwords inside script files or push them to public repositories.
- **Environment Variables**: Use external configuration files, environment variables, or secure credential stores to supply credentials at runtime.
- **Dry-Run Default**: Always test strategies in paper-trading/demo mode before connecting real account funds.

---

## Project Structure (Overview)

```
AdaptiveGridBot/
├── market_data.py                    # Market data ingestion & indicator processing
├── grid_engine.py                    # Grid level generation & dynamic adjustment
├── order_manager.py                  # Order lifecycle & state reconciliation
├── risk_engine.py                    # Risk limits, exposure capping & safety halts
├── account_manager.py                # Balance tracking & margin status
├── adaptive_grid_dashboard.py        # Web telemetry & monitoring dashboard
├── adaptive_grid_bot_A_btc.py        # BTC bot experiment variant
├── adaptive_grid_bot_D_eth.py        # ETH bot experiment variant
├── adaptive_grid_bot_G_sol.py        # SOL bot experiment variant
├── adaptive_grid_v048_demo_smart_loop.py # Generation 4.8 smart loop runner
├── adaptive_grid_v0511_demo_smart_loop_FULL.py # Generation 5.1.1 full implementation
├── backtest_v048_realized_pnl.py     # Realized PnL backtest module
├── backtest_v050_multi_walkforward.py# Walk-forward optimization engine
├── requirements_v048.txt            # Sample dependency manifest
└── ...
```

---

## Development Status

This repository is an **active research and experimental workspace**. It contains historical scripts, prototype iterations, backtest variations, and experimental variants accumulated over multiple development cycles. Code structure and script parameterizations reflect specific experimental setups.

---

## AI-Assisted Development

Portions of this codebase, backtesting frameworks, and architectural components were designed, refined, and documented using AI-assisted development tools and automated coding workflows.

---

## License & Disclaimer

### Disclaimer

> **This project is strictly for research, experimentation, backtesting, and educational purposes.**
>
> Algorithmic trading and cryptocurrency markets involve substantial financial risk. The authors and contributors bear no responsibility for any financial loss, unintended bot behavior, or execution errors. Users are solely responsible for verifying their own API credentials, risk limits, configuration parameters, and trading decisions.

### License

License: Not specified yet.
