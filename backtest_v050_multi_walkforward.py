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
LEVELS = 10
REBUILD_LEVELS = 5

# v5 candidate neighborhood
GRIDS = [0.0030, 0.0040, 0.0050, 0.0060, 0.0070]
SIZES = [10.0, 15.0, 20.0]
SELL_MULTS = [1.5, 2.0, 2.5, 3.0]


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
        raise RuntimeError("Not enough 1H data.")

    return h


def simulate(data, grid, size, sell_mult):
    cash = CAPITAL
    btc = 0.0
    anchor = float(data.iloc[0]["open"])
    curve = []
    trades = 0
    fees = 0.0
    buys = 0
    sells = 0

    for _, r in data.iterrows():
        o, hi, lo, close = map(
            float, [r["open"], r["high"], r["low"], r["close"]]
        )

        bullish = float(r["ema50"]) > float(r["ema200"])

        # Dynamic grid from volatility regime.
        atr_pct = (
            float(r["atr30"]) / close
            if pd.notna(r["atr30"]) and close > 0
            else grid
        )

        if atr_pct >= 0.025:
            regime_grid = max(grid, 0.0050)
        elif atr_pct >= 0.020:
            regime_grid = max(grid, 0.0040)
        else:
            regime_grid = max(grid, 0.0030)

        buy_step = regime_grid if bullish else regime_grid * sell_mult
        sell_step = regime_grid * sell_mult if bullish else regime_grid

        buy_levels = [
            anchor * (1 - buy_step * i)
            for i in range(1, LEVELS + 1)
        ]
        sell_levels = [
            anchor * (1 + sell_step * i)
            for i in range(1, LEVELS + 1)
        ]

        hit_b = [p for p in buy_levels if lo <= p]
        hit_s = [p for p in sell_levels if hi >= p]

        side = None
        price = None

        # Conservative one fill per candle.
        if close >= o:
            if hit_b:
                side, price = "BUY", max(hit_b)
            elif hit_s and btc > 0:
                side, price = "SELL", min(hit_s)
        else:
            if hit_s and btc > 0:
                side, price = "SELL", min(hit_s)
            elif hit_b:
                side, price = "BUY", max(hit_b)

        # v5 profit filter: only BUY if the configured grid itself
        # clears round-trip fee + slippage + safety margin.
        min_profitable = 2 * (FEE + SLIPPAGE) + 0.0010
        if side == "BUY" and buy_step < min_profitable:
            side = None

        if side == "BUY":
            exec_price = price * (1 + SLIPPAGE)
            qty = size / exec_price
            fee = size * FEE

            if (
                cash >= size + fee
                and btc * close + size <= INVENTORY_CAP
            ):
                cash -= size + fee
                btc += qty
                fees += fee
                buys += 1
                trades += 1

        elif side == "SELL" and btc > 0:
            qty = min(size / price, btc)
            if qty > 0:
                gross = qty * price
                fee = gross * FEE
                cash += gross - fee
                btc -= qty
                fees += fee
                sells += 1
                trades += 1

        curve.append(cash + btc * close)

        if abs(close - anchor) >= REBUILD_LEVELS * regime_grid * anchor:
            anchor = close

    curve = np.asarray(curve)
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


def pick_train(train):
    rows = []

    for grid, size, mult in itertools.product(
        GRIDS, SIZES, SELL_MULTS
    ):
        r = simulate(train, grid, size, mult)
        days = max(
            (train.iloc[-1]["timestamp"] - train.iloc[0]["timestamp"]).total_seconds() / 86400,
            1 / 24,
        )

        # Robust train score: profit/day with DD and excessive-trade penalties.
        score = (
            r["pnl_day"]
            - abs(r["dd"]) * 0.20
            - (r["trades"] / days) * 0.0005
        )

        rows.append({
            "grid": grid,
            "size": size,
            "mult": mult,
            "train_pnl": r["pnl"],
            "train_pnl_day": r["pnl_day"],
            "train_dd": r["dd"],
            "train_trades": r["trades"],
            "score": score,
        })

    return pd.DataFrame(rows).sort_values(
        "score", ascending=False
    )


def main():
    data = load()

    # Rolling unseen-test windows.
    windows = [
        ("W1", 10, 5),
        ("W2", 15, 5),
        ("W3", 20, 10),
    ]

    rows = []

    for name, train_days, test_days in windows:
        end = data["timestamp"].max()
        test_start = end - pd.Timedelta(days=test_days)
        train_start = test_start - pd.Timedelta(days=train_days)

        train = data[
            (data["timestamp"] >= train_start)
            & (data["timestamp"] < test_start)
        ].copy()

        test = data[
            data["timestamp"] >= test_start
        ].copy()

        ranked = pick_train(train)
        chosen = ranked.iloc[0]

        test_r = simulate(
            test,
            float(chosen["grid"]),
            float(chosen["size"]),
            float(chosen["mult"]),
        )

        days = max(
            (test.iloc[-1]["timestamp"] - test.iloc[0]["timestamp"]).total_seconds() / 86400,
            1 / 24,
        )

        bh = (
            CAPITAL
            * float(test.iloc[-1]["close"])
            / float(test.iloc[0]["open"])
            - CAPITAL
        )

        rows.append({
            "window": name,
            "train_days": train_days,
            "test_days": test_days,
            "grid_pct": chosen["grid"] * 100,
            "order_size": chosen["size"],
            "sell_mult": chosen["mult"],
            "train_pnl": chosen["train_pnl"],
            "train_pnl_day": chosen["train_pnl_day"],
            "test_pnl": test_r["pnl"],
            "test_pnl_day": test_r["pnl_day"],
            "test_dd": test_r["dd"],
            "test_trades": test_r["trades"],
            "test_fees": test_r["fees"],
            "test_final_btc": test_r["final_btc"],
            "buy_hold": bh,
            "alpha_vs_bh": test_r["pnl"] - bh,
        })

    out = pd.DataFrame(rows)

    ts = pd.Timestamp.now(tz="UTC").strftime("%Y%m%d_%H%M%S")
    csv = BASE / f"v50_multi_walkforward_{ts}.csv"
    out.to_csv(csv, index=False)

    print()
    print("=" * 76)
    print("       ADAPTIVE GRID BOT v5.0 - MULTI WALK-FORWARD")
    print("=" * 76)
    print("Dynamic volatility grid + fee/slippage profit filter")
    print("Parameters selected only from TRAIN.")
    print("TEST remains unseen.")
    print()

    print(out.to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}"
    ))

    positive = int((out["test_pnl"] > 0).sum())

    print()
    print("ROBUSTNESS")
    print("-" * 76)
    print(f"Positive TEST windows : {positive}/{len(out)}")
    print(f"Total TEST P/L        : {out['test_pnl'].sum():+.6f} USDT")
    print(f"Average P/L/day       : {out['test_pnl_day'].mean():+.6f} USDT")
    print(f"Worst TEST DD         : {out['test_dd'].min():.4f}%")
    print(f"Total TEST fees       : {out['test_fees'].sum():.6f} USDT")

    print()
    print("SELECTED PARAMETERS")
    for _, r in out.iterrows():
        print(
            f"{r['window']}: "
            f"Grid {r['grid_pct']:.2f}% | "
            f"${r['order_size']:.0f} | "
            f"SELL {r['sell_mult']:.1f}x"
        )

    print()
    print(f"CSV: {csv.name}")

    if positive == len(out):
        print()
        print("PASS: all TEST windows positive.")
        print("Next: build v5 Demo Smart Loop using .env.v50.")
    else:
        print()
        print("NOT ROBUST YET: do not deploy v5.")


if __name__ == "__main__":
    main()
