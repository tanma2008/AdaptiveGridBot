import itertools
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
H1 = BASE / "btc_usdt_1h.csv"
D1 = BASE / "btc_usdt_1d.csv"

CAPITAL = 1000.0
INVENTORY_CAP = 1050.0
FEE = 0.0008
SLIPPAGE = 0.00005

GRIDS = [0.0020, 0.0025, 0.0030, 0.0035, 0.0040, 0.0050, 0.0060]
SIZES = [10.0, 15.0, 20.0]
SELL_MULTS = [1.0, 1.5, 2.0, 2.5, 3.0]

LEVELS = 10
REBUILD_LEVELS = 5


def load():
    h = pd.read_csv(H1, parse_dates=["timestamp"]).sort_values("timestamp")
    h = h[pd.to_numeric(h["confirm"], errors="coerce") == 1].copy()

    d = pd.read_csv(D1, parse_dates=["timestamp"]).sort_values("timestamp")
    d = d[pd.to_numeric(d["confirm"], errors="coerce") == 1].copy()

    h["ema50"] = h["close"].ewm(span=50, adjust=False).mean()
    h["ema200"] = h["close"].ewm(span=200, adjust=False).mean()

    prev = d["close"].shift(1)
    tr = pd.concat([
        d["high"] - d["low"],
        (d["high"] - prev).abs(),
        (d["low"] - prev).abs(),
    ], axis=1).max(axis=1)
    d["atr30"] = tr.rolling(30).mean()

    h = h.merge(d[["timestamp", "atr30"]], on="timestamp", how="left")
    h["atr30"] = h["atr30"].ffill()

    end = h["timestamp"].max()
    h = h[h["timestamp"] >= end - pd.Timedelta(days=30)].reset_index(drop=True)

    if len(h) < 24 * 25:
        raise RuntimeError("Not enough 1H data for 30D test.")

    return h


def simulate(data, grid, size, sell_mult, min_spread):
    cash = CAPITAL
    btc = 0.0
    anchor = float(data.iloc[0]["open"])

    equity = []
    trades = 0
    buys = 0
    sells = 0
    fees = 0.0

    for _, r in data.iterrows():
        o, hi, lo, close = map(float, [r["open"], r["high"], r["low"], r["close"]])
        bullish = float(r["ema50"]) > float(r["ema200"])

        buy_step = grid if bullish else grid * sell_mult
        sell_step = grid * sell_mult if bullish else grid

        buy_levels = [anchor * (1 - buy_step * i) for i in range(1, LEVELS + 1)]
        sell_levels = [anchor * (1 + sell_step * i) for i in range(1, LEVELS + 1)]

        hits_b = [p for p in buy_levels if lo <= p]
        hits_s = [p for p in sell_levels if hi >= p]

        side = None
        price = None

        # Conservative one-fill-per-candle sequencing.
        if close >= o:
            if hits_b:
                side, price = "BUY", max(hits_b)
            elif hits_s and btc > 0:
                side, price = "SELL", min(hits_s)
        else:
            if hits_s and btc > 0:
                side, price = "SELL", min(hits_s)
            elif hits_b:
                side, price = "BUY", max(hits_b)

        if side == "BUY":
            # Minimum expected round-trip edge:
            # grid distance must cover both fees + slippage + safety buffer.
            # Here min_spread is the required price distance.
            if buy_step < min_spread:
                side = None

        if side == "BUY":
            exec_price = price * (1 + SLIPPAGE)
            qty = size / exec_price
            fee = size * FEE

            if cash >= size + fee and btc * close + size <= INVENTORY_CAP:
                cash -= size + fee
                btc += qty
                fees += fee
                trades += 1
                buys += 1

        elif side == "SELL":
            qty = min(size / price, btc)
            if qty > 0:
                gross = qty * price
                fee = gross * FEE
                cash += gross - fee
                btc -= qty
                fees += fee
                trades += 1
                sells += 1

        eq = cash + btc * close
        equity.append(eq)

        if abs(close - anchor) >= REBUILD_LEVELS * grid * anchor:
            anchor = close

    curve = np.asarray(equity)
    peak = np.maximum.accumulate(curve)
    dd = (curve - peak) / peak

    days = max(
        (data.iloc[-1]["timestamp"] - data.iloc[0]["timestamp"]).total_seconds() / 86400,
        1 / 24,
    )

    pnl = float(curve[-1] - CAPITAL)

    return {
        "pnl": pnl,
        "pnl_day": pnl / days,
        "trades": trades,
        "buys": buys,
        "sells": sells,
        "fees": fees,
        "dd": float(dd.min() * 100),
        "final_btc": btc,
    }


def main():
    data = load()

    # Test the exact 12H period represented by the current demo analysis
    # only if it falls inside the available historical data.
    end = data["timestamp"].max()
    last12 = data[data["timestamp"] >= end - pd.Timedelta(hours=12)].copy()

    # 30D full sweep
    rows = []

    for grid, size, mult, min_spread in itertools.product(
        GRIDS, SIZES, SELL_MULTS, GRIDS
    ):
        # Don't allow a minimum spread below the actual grid step.
        if min_spread > grid:
            continue

        r = simulate(data, grid, size, mult, min_spread)

        rows.append({
            "grid_pct": grid * 100,
            "order_size": size,
            "sell_mult": mult,
            "min_spread_pct": min_spread * 100,
            **r,
        })

    out = pd.DataFrame(rows)

    # Rank for net P/L/day, with DD as secondary criterion.
    out = out.sort_values(
        ["pnl_day", "dd"],
        ascending=[False, False]
    )

    ts = pd.Timestamp.now(tz="UTC").strftime("%Y%m%d_%H%M%S")
    full_csv = BASE / f"v50_30d_profit_filter_optimizer_{ts}.csv"
    out.to_csv(full_csv, index=False)

    # Best 12H candidates using same v50 logic.
    short_rows = []
    for grid, size, mult, min_spread in itertools.product(
        GRIDS, SIZES, SELL_MULTS, GRIDS
    ):
        if min_spread > grid:
            continue
        r = simulate(last12, grid, size, mult, min_spread)
        short_rows.append({
            "grid_pct": grid * 100,
            "order_size": size,
            "sell_mult": mult,
            "min_spread_pct": min_spread * 100,
            **r,
        })

    short = pd.DataFrame(short_rows).sort_values(
        ["pnl", "dd"], ascending=[False, False]
    )
    short_csv = BASE / f"v50_12h_profit_filter_sim_{ts}.csv"
    short.to_csv(short_csv, index=False)

    print()
    print("=" * 76)
    print("       ADAPTIVE GRID BOT v5.0 - PROFIT FILTER OPTIMIZER")
    print("=" * 76)
    print(f"30D: {data.iloc[0]['timestamp']} -> {data.iloc[-1]['timestamp']}")
    print(f"12H: {last12.iloc[0]['timestamp']} -> {last12.iloc[-1]['timestamp']}")
    print(f"Fee/side: {FEE*100:.3f}% | Slippage/side: {SLIPPAGE*100:.3f}%")
    print()
    print("TOP 10 - 30D")
    print("-" * 76)
    print(out[[
        "grid_pct", "order_size", "sell_mult", "min_spread_pct",
        "pnl", "pnl_day", "trades", "fees", "dd"
    ]].head(10).to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    print()
    print("TOP 10 - SAME v5 LOGIC ON LAST 12H")
    print("-" * 76)
    print(short[[
        "grid_pct", "order_size", "sell_mult", "min_spread_pct",
        "pnl", "pnl_day", "trades", "fees", "dd"
    ]].head(10).to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    best = out.iloc[0]
    print()
    print("BEST 30D CANDIDATE")
    print("-" * 76)
    print(f"Grid             : {best['grid_pct']:.2f}%")
    print(f"Order size       : ${best['order_size']:.2f}")
    print(f"SELL multiplier  : {best['sell_mult']:.2f}x")
    print(f"Min spread       : {best['min_spread_pct']:.2f}%")
    print(f"Net P/L          : {best['pnl']:+.6f} USDT")
    print(f"Net P/L/day      : {best['pnl_day']:+.6f} USDT")
    print(f"Max drawdown     : {best['dd']:.4f}%")
    print(f"Trades           : {int(best['trades'])}")
    print()
    print(f"30D CSV          : {full_csv.name}")
    print(f"12H CSV          : {short_csv.name}")
    print()
    print("RESEARCH ONLY - NO ORDERS CREATED.")
    print("Do not use .env.v50 until walk-forward validation passes.")


if __name__ == "__main__":
    main()
