import itertools
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
FILE_1H = BASE_DIR / "btc_usdt_1h.csv"
FILE_1D = BASE_DIR / "btc_usdt_1d.csv"

CAPITAL = 1000.0
INVENTORY_CAP = 1050.0
FEE = 0.0008
SLIPPAGE = 0.00005

# Candidate family around the robust B result, plus nearby values.
GRID_CANDIDATES = [0.004, 0.005, 0.006, 0.007, 0.008]
ORDER_SIZE_CANDIDATES = [10.0, 15.0, 20.0]
SELL_MULT_CANDIDATES = [2.0, 2.5, 3.0]

LEVELS = 10
REBUILD_LEVELS = 5


def load_data():
    h = pd.read_csv(FILE_1H, parse_dates=["timestamp"]).sort_values("timestamp")
    h = h[pd.to_numeric(h["confirm"], errors="coerce") == 1].copy()

    d = pd.read_csv(FILE_1D, parse_dates=["timestamp"]).sort_values("timestamp")
    d = d[pd.to_numeric(d["confirm"], errors="coerce") == 1].copy()

    h["ema50"] = h["close"].ewm(span=50, adjust=False).mean()
    h["ema200"] = h["close"].ewm(span=200, adjust=False).mean()

    prev = d["close"].shift(1)
    tr = pd.concat(
        [
            d["high"] - d["low"],
            (d["high"] - prev).abs(),
            (d["low"] - prev).abs(),
        ],
        axis=1,
    ).max(axis=1)

    d["atr30"] = tr.rolling(30).mean()

    # Exact timestamp only; forward-fill ATR from already-known daily values.
    h = h.merge(d[["timestamp", "atr30"]], on="timestamp", how="left")
    h["atr30"] = h["atr30"].ffill()

    end = h["timestamp"].max()
    start = end - pd.Timedelta(days=30)
    h = h[h["timestamp"] >= start].reset_index(drop=True)

    if len(h) < 24 * 25:
        raise RuntimeError("Not enough 1H data for 30D validation.")

    return h


def simulate(data, grid, size, sell_mult):
    cash = CAPITAL
    btc = 0.0
    anchor = float(data.iloc[0]["open"])
    curve = []
    trades = 0
    fees = 0.0
    wins_proxy = 0

    for _, row in data.iterrows():
        o = float(row["open"])
        hi = float(row["high"])
        lo = float(row["low"])
        close = float(row["close"])

        bullish = float(row["ema50"]) > float(row["ema200"])

        buy_grid = grid if bullish else grid * sell_mult
        sell_grid = grid * sell_mult if bullish else grid

        buys = [anchor * (1 - buy_grid * i) for i in range(1, LEVELS + 1)]
        sells = [anchor * (1 + sell_grid * i) for i in range(1, LEVELS + 1)]

        hit_buys = [p for p in buys if lo <= p]
        hit_sells = [p for p in sells if hi >= p]

        side = None
        price = None

        # One fill/candle to avoid optimistic intrabar sequencing.
        if close >= o:
            if hit_buys:
                side, price = "BUY", max(hit_buys)
            elif hit_sells and btc > 0:
                side, price = "SELL", min(hit_sells)
        else:
            if hit_sells and btc > 0:
                side, price = "SELL", min(hit_sells)
            elif hit_buys:
                side, price = "BUY", max(hit_buys)

        if side == "BUY":
            exec_price = price * (1 + SLIPPAGE)
            qty = size / exec_price
            fee = size * FEE
            cost = size + fee

            if cash >= cost and btc * close + size <= INVENTORY_CAP:
                cash -= cost
                btc += qty
                fees += fee
                trades += 1

        elif side == "SELL" and btc > 0:
            qty = min(size / price, btc)
            gross = qty * price
            fee = gross * FEE

            cash += gross - fee
            btc -= qty
            fees += fee
            trades += 1

        equity = cash + btc * close
        curve.append(equity)

        if abs(close - anchor) >= REBUILD_LEVELS * grid * anchor:
            anchor = close

    curve = np.asarray(curve)
    peak = np.maximum.accumulate(curve)
    dd = (curve - peak) / peak

    return {
        "pnl": float(curve[-1] - CAPITAL),
        "trades": trades,
        "fees": fees,
        "max_dd": float(dd.min() * 100),
        "final_equity": float(curve[-1]),
        "final_btc": btc,
    }


def score(r, days):
    # Robustness score: positive net/day, penalize drawdown and excessive trading.
    pnl_day = r["pnl"] / days
    dd_penalty = abs(r["max_dd"]) * 0.20
    trade_penalty = (r["trades"] / days) * 0.0005
    return pnl_day - dd_penalty - trade_penalty


def main():
    data = load_data()

    # Three rolling walk-forward windows:
    # W1: train 10D / test 5D
    # W2: train 15D / test 5D
    # W3: train 20D / test 10D
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

        # Select candidate only from TRAIN.
        train_results = []

        for grid, size, mult in itertools.product(
            GRID_CANDIDATES,
            ORDER_SIZE_CANDIDATES,
            SELL_MULT_CANDIDATES,
        ):
            r = simulate(train, grid, size, mult)
            days = max(
                (train.iloc[-1]["timestamp"] - train.iloc[0]["timestamp"]).total_seconds() / 86400,
                1 / 24,
            )

            train_results.append(
                {
                    "grid": grid,
                    "size": size,
                    "mult": mult,
                    "train_pnl": r["pnl"],
                    "train_pnl_day": r["pnl"] / days,
                    "train_dd": r["max_dd"],
                    "train_trades": r["trades"],
                    "score": score(r, days),
                }
            )

        tr = pd.DataFrame(train_results).sort_values(
            "score", ascending=False
        )

        # Test only the best TRAIN candidate.
        chosen = tr.iloc[0]

        test_r = simulate(
            test,
            float(chosen["grid"]),
            float(chosen["size"]),
            float(chosen["mult"]),
        )

        test_days = max(
            (test.iloc[-1]["timestamp"] - test.iloc[0]["timestamp"]).total_seconds() / 86400,
            1 / 24,
        )

        bh = (
            CAPITAL
            * float(test.iloc[-1]["close"])
            / float(test.iloc[0]["open"])
            - CAPITAL
        )

        rows.append(
            {
                "window": name,
                "train_days": train_days,
                "test_days": test_days,
                "train_start": str(train.iloc[0]["timestamp"]),
                "train_end": str(train.iloc[-1]["timestamp"]),
                "test_start": str(test.iloc[0]["timestamp"]),
                "test_end": str(test.iloc[-1]["timestamp"]),
                "grid_pct": float(chosen["grid"]) * 100,
                "order_size": float(chosen["size"]),
                "sell_mult": float(chosen["mult"]),
                "train_pnl": float(chosen["train_pnl"]),
                "train_pnl_day": float(chosen["train_pnl_day"]),
                "train_dd": float(chosen["train_dd"]),
                "test_pnl": test_r["pnl"],
                "test_pnl_day": test_r["pnl"] / test_days,
                "test_trades": test_r["trades"],
                "test_fees": test_r["fees"],
                "test_dd": test_r["max_dd"],
                "test_buy_hold": bh,
                "test_alpha": test_r["pnl"] - bh,
            }
        )

    out = pd.DataFrame(rows)

    ts = pd.Timestamp.now(tz="UTC").strftime("%Y%m%d_%H%M%S")
    csv_path = BASE_DIR / f"v05_multi_walkforward_{ts}.csv"
    out.to_csv(csv_path, index=False)

    print()
    print("=" * 76)
    print("       ADAPTIVE GRID BOT v5 - MULTI WALK-FORWARD")
    print("=" * 76)
    print("Candidate selection happens ONLY inside each TRAIN window.")
    print("TEST data is unseen during selection.")
    print()

    print(
        out[
            [
                "window",
                "grid_pct",
                "order_size",
                "sell_mult",
                "train_pnl",
                "test_pnl",
                "test_pnl_day",
                "test_dd",
                "test_trades",
                "test_alpha",
            ]
        ].to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    print()
    print("ROBUSTNESS SUMMARY")
    print("-" * 76)

    positive = int((out["test_pnl"] > 0).sum())
    total = len(out)

    print(f"Positive TEST windows : {positive}/{total}")
    print(f"Total TEST P/L        : {out['test_pnl'].sum():+.6f} USDT")
    print(f"Average TEST P/L/day  : {out['test_pnl_day'].mean():+.6f} USDT")
    print(f"Worst TEST drawdown   : {out['test_dd'].min():.4f}%")
    print(f"Total TEST fees       : {out['test_fees'].sum():.6f} USDT")

    # Candidate consistency
    print()
    print("Selected parameters by window:")
    for _, r in out.iterrows():
        print(
            f"  {r['window']}: "
            f"{r['grid_pct']:.2f}% / "
            f"${r['order_size']:.0f} / "
            f"{r['sell_mult']:.1f}x"
        )

    print()
    print(f"CSV: {csv_path.name}")

    if positive == total:
        print()
        print("PASS CANDIDATE: positive TEST in every window.")
        print("Next: build v5 Demo Smart Loop with .env.v50.")
    else:
        print()
        print("NOT YET ROBUST: at least one TEST window is negative.")
        print("Do not deploy v5 yet.")


if __name__ == "__main__":
    main()
