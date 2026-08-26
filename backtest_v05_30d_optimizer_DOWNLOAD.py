import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# AdaptiveGridBot v5 - 30D Optimizer
# ============================================================
# PURPOSE:
#   Find candidate Grid / Order Size parameters for v5.
#
# IMPORTANT:
#   This is a conservative research backtest, NOT live trading code.
#   It uses only information available before each 1H candle.
#   Fee + slippage are included.
#
#   v5 Demo will use .env.v50 separately.
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

FILE_1H = BASE_DIR / "btc_usdt_1h.csv"
FILE_1D = BASE_DIR / "btc_usdt_1d.csv"

CAPITAL_USDT = 1000.0
INVENTORY_CAP_USDT = 1050.0

FEE_RATE = 0.0008       # 0.08% per side
SLIPPAGE = 0.00005      # 0.005% per side

GRID_CANDIDATES = [
    0.0010, 0.0015, 0.0020, 0.0025,
    0.0030, 0.0040, 0.0050, 0.0060,
    0.0080, 0.0100,
]

ORDER_SIZE_CANDIDATES = [
    5.0, 7.5, 10.0, 15.0, 20.0
]

SELL_MULT_CANDIDATES = [
    1.0, 1.5, 2.0, 2.5, 3.0
]

LEVELS = 10
REBUILD_LEVELS = 5


def load_data():
    h = pd.read_csv(FILE_1H, parse_dates=["timestamp"])
    h = h.sort_values("timestamp")
    h = h[pd.to_numeric(h["confirm"], errors="coerce") == 1].copy()

    d = pd.read_csv(FILE_1D, parse_dates=["timestamp"])
    d = d.sort_values("timestamp")
    d = d[pd.to_numeric(d["confirm"], errors="coerce") == 1].copy()

    # Hourly EMA
    h["ema50"] = h["close"].ewm(
        span=50, adjust=False
    ).mean()

    h["ema200"] = h["close"].ewm(
        span=200, adjust=False
    ).mean()

    # Daily ATR(30)
    prev_close = d["close"].shift(1)

    tr = pd.concat(
        [
            d["high"] - d["low"],
            (d["high"] - prev_close).abs(),
            (d["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    d["atr30"] = tr.rolling(30).mean()

    h = h.merge(
        d[["timestamp", "atr30"]],
        on="timestamp",
        how="left",
    )

    h["atr30"] = h["atr30"].ffill()

    # Last 30 calendar days available in the 1H dataset
    end = h["timestamp"].max()
    start = end - pd.Timedelta(days=30)

    h = h[h["timestamp"] >= start].copy()
    h = h.reset_index(drop=True)

    if len(h) < 24 * 25:
        raise RuntimeError(
            f"Not enough 1H data for 30D test: {len(h)} rows"
        )

    return h


def simulate(
    data,
    base_grid,
    order_size,
    sell_mult,
):
    cash = CAPITAL_USDT
    btc = 0.0
    anchor = float(data.iloc[0]["open"])

    equity_curve = []
    trades = 0

    for _, row in data.iterrows():

        o = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])

        bullish = float(row["ema50"]) > float(row["ema200"])

        # Trend-aware asymmetric grid.
        # Bull trend:
        #   normal BUY grid
        #   wider SELL grid to avoid dumping BTC too early
        #
        # Bear trend:
        #   wider BUY grid
        #   normal SELL grid
        if bullish:
            buy_grid = base_grid
            sell_grid = base_grid * sell_mult
        else:
            buy_grid = base_grid * sell_mult
            sell_grid = base_grid

        buy_levels = [
            anchor * (1.0 - buy_grid * i)
            for i in range(1, LEVELS + 1)
        ]

        sell_levels = [
            anchor * (1.0 + sell_grid * i)
            for i in range(1, LEVELS + 1)
        ]

        touched_buys = [
            p for p in buy_levels
            if low <= p
        ]

        touched_sells = [
            p for p in sell_levels
            if high >= p
        ]

        # OHLC cannot tell us exact intrabar order.
        # Use a conservative one-fill-per-candle rule.
        side = None
        price = None

        if close >= o:
            # bullish candle: low -> high assumption
            if touched_buys:
                side = "BUY"
                price = max(touched_buys)
            elif touched_sells and btc > 0:
                side = "SELL"
                price = min(touched_sells)

        else:
            # bearish candle: high -> low assumption
            if touched_sells and btc > 0:
                side = "SELL"
                price = min(touched_sells)
            elif touched_buys:
                side = "BUY"
                price = max(touched_buys)

        if side == "BUY":

            total_cost = order_size * (1.0 + FEE_RATE)

            inventory_value = btc * close

            if (
                cash >= total_cost
                and inventory_value + order_size
                <= INVENTORY_CAP_USDT
            ):
                exec_price = price * (1.0 + SLIPPAGE)
                qty = order_size / exec_price

                cash -= total_cost
                btc += qty
                trades += 1

        elif side == "SELL":

            qty = min(
                order_size / price,
                btc,
            )

            if qty > 0:

                gross = qty * price

                cash += gross * (1.0 - FEE_RATE)
                btc -= qty
                trades += 1

        equity = cash + btc * close
        equity_curve.append(equity)

        # Grid HOLD / rebuild rule.
        if (
            abs(close - anchor)
            >= REBUILD_LEVELS * base_grid * anchor
        ):
            anchor = close

    curve = np.asarray(equity_curve)

    peak = np.maximum.accumulate(curve)

    drawdown = (
        curve - peak
    ) / peak

    final_equity = float(curve[-1])

    pnl = final_equity - CAPITAL_USDT

    return {
        "pnl": pnl,
        "final_equity": final_equity,
        "trades": trades,
        "final_btc": btc,
        "max_drawdown": float(drawdown.min()),
    }


def main():

    data = load_data()

    start = data.iloc[0]["timestamp"]
    end = data.iloc[-1]["timestamp"]

    buy_hold = (
        CAPITAL_USDT
        * float(data.iloc[-1]["close"])
        / float(data.iloc[0]["open"])
        - CAPITAL_USDT
    )

    results = []

    for grid, size, sell_mult in itertools.product(
        GRID_CANDIDATES,
        ORDER_SIZE_CANDIDATES,
        SELL_MULT_CANDIDATES,
    ):

        r = simulate(
            data,
            grid,
            size,
            sell_mult,
        )

        results.append({
            "grid_pct": grid * 100.0,
            "grid": grid,
            "order_size_usdt": size,
            "bull_sell_multiplier": sell_mult,
            "pnl_usdt": r["pnl"],
            "final_equity_usdt": r["final_equity"],
            "trades": r["trades"],
            "final_btc": r["final_btc"],
            "max_drawdown_pct": r["max_drawdown"] * 100.0,
            "alpha_vs_buy_hold_usdt": r["pnl"] - buy_hold,
        })

    result = pd.DataFrame(results)

    # Primary objective:
    #   maximize net P/L while preferring smaller drawdown.
    #
    # We still print the raw P/L ranking separately.
    result = result.sort_values(
        [
            "pnl_usdt",
            "max_drawdown_pct",
        ],
        ascending=[False, False],
    )

    timestamp = pd.Timestamp.utcnow().strftime(
        "%Y%m%d_%H%M%S"
    )

    csv_name = (
        BASE_DIR
        / f"v05_30d_optimizer_{timestamp}.csv"
    )

    config_name = (
        BASE_DIR
        / "v05_optimized_config.json"
    )

    result.to_csv(
        csv_name,
        index=False,
    )

    top = result.iloc[0].to_dict()

    config = {
        "version": "v5-research-candidate",
        "approved_for_live": False,
        "reason": (
            "Candidate generated by 30D historical optimizer. "
            "Must pass forward demo validation before live use."
        ),
        "period_start": str(start),
        "period_end": str(end),
        "capital_usdt": CAPITAL_USDT,
        "inventory_cap_usdt": INVENTORY_CAP_USDT,
        "fee_rate": FEE_RATE,
        "slippage": SLIPPAGE,
        "grid": float(top["grid"]),
        "grid_pct": float(top["grid_pct"]),
        "order_size_usdt": float(
            top["order_size_usdt"]
        ),
        "bull_sell_multiplier": float(
            top["bull_sell_multiplier"]
        ),
        "levels": LEVELS,
        "rebuild_levels": REBUILD_LEVELS,
        "backtest_pnl_usdt": float(
            top["pnl_usdt"]
        ),
        "backtest_max_drawdown_pct": float(
            top["max_drawdown_pct"]
        ),
        "buy_hold_pnl_usdt": float(
            buy_hold
        ),
        "alpha_vs_buy_hold_usdt": float(
            top["alpha_vs_buy_hold_usdt"]
        ),
    }

    with open(
        config_name,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            config,
            f,
            indent=2,
        )

    print()
    print("=" * 76)
    print("       ADAPTIVE GRID BOT v5 - 30D OPTIMIZER")
    print("=" * 76)

    print(f"Period       : {start} -> {end}")
    print(f"Capital      : ${CAPITAL_USDT:,.2f}")
    print(f"Fee / side   : {FEE_RATE * 100:.3f}%")
    print(f"Slippage     : {SLIPPAGE * 100:.3f}%")
    print()

    print("BUY & HOLD BENCHMARK")
    print("-" * 76)
    print(
        f"P/L          : "
        f"{buy_hold:+.6f} USDT"
    )

    print()
    print("TOP 10 CANDIDATES")
    print("-" * 76)

    cols = [
        "grid_pct",
        "order_size_usdt",
        "bull_sell_multiplier",
        "pnl_usdt",
        "max_drawdown_pct",
        "trades",
        "alpha_vs_buy_hold_usdt",
    ]

    print(
        result[cols]
        .head(10)
        .to_string(
            index=False,
            float_format=lambda v: f"{v:.4f}",
        )
    )

    print()
    print("BEST CANDIDATE")
    print("-" * 76)

    print(
        f"Grid             : "
        f"{top['grid_pct']:.4f}%"
    )

    print(
        f"Order size       : "
        f"${top['order_size_usdt']:.2f}"
    )

    print(
        f"Bull sell mult.  : "
        f"{top['bull_sell_multiplier']:.2f}x"
    )

    print(
        f"Net P/L          : "
        f"{top['pnl_usdt']:+.6f} USDT"
    )

    print(
        f"Max drawdown     : "
        f"{top['max_drawdown_pct']:.4f}%"
    )

    print(
        f"Trades           : "
        f"{int(top['trades'])}"
    )

    print(
        f"vs Buy & Hold    : "
        f"{top['alpha_vs_buy_hold_usdt']:+.6f} USDT"
    )

    print()
    print("OUTPUT")
    print("-" * 76)
    print(f"Optimizer CSV    : {csv_name.name}")
    print(f"Config           : {config_name.name}")

    print()
    print(
        "IMPORTANT: v5 is NOT approved for live trading yet."
    )
    print(
        "Next step: walk-forward / forward Demo validation "
        "using .env.v50."
    )


if __name__ == "__main__":
    main()
