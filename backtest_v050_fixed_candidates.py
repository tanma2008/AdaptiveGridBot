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

# Fixed candidates: NO per-window optimizer selection.
CANDIDATES = [
    ("A", 0.0030, 20.0, 1.5),
    ("B", 0.0040, 20.0, 2.0),
    ("C", 0.0050, 15.0, 2.5),
    ("D", 0.0060, 15.0, 2.5),
    ("E", 0.0060, 20.0, 2.5),
]


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
        o, hi, lo, close = map(float, [r["open"], r["high"], r["low"], r["close"]])
        bullish = float(r["ema50"]) > float(r["ema200"])

        atr_pct = float(r["atr30"]) / close if pd.notna(r["atr30"]) and close > 0 else grid

        # Dynamic regime multiplier, but never tighter than candidate grid.
        if atr_pct >= 0.025:
            regime_grid = max(grid, 0.0050)
        elif atr_pct >= 0.020:
            regime_grid = max(grid, 0.0040)
        else:
            regime_grid = max(grid, 0.0030)

        buy_step = regime_grid if bullish else regime_grid * sell_mult
        sell_step = regime_grid * sell_mult if bullish else regime_grid

        buy_levels = [anchor * (1 - buy_step * i) for i in range(1, LEVELS + 1)]
        sell_levels = [anchor * (1 + sell_step * i) for i in range(1, LEVELS + 1)]

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

        # Fee + slippage + 0.10% safety buffer.
        min_profitable = 2 * (FEE + SLIPPAGE) + 0.0010
        if side == "BUY" and buy_step < min_profitable:
            side = None

        if side == "BUY":
            exec_price = price * (1 + SLIPPAGE)
            qty = size / exec_price
            fee = size * FEE
            if cash >= size + fee and btc * close + size <= INVENTORY_CAP:
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
        "fees": fees,
        "dd": float(dd.min() * 100),
        "final_btc": btc,
        "buys": buys,
        "sells": sells,
    }


def main():
    data = load()
    end = data["timestamp"].max()

    # Five unseen test windows, fixed candidates evaluated identically.
    windows = [
        ("W1", 10, 5),
        ("W2", 15, 5),
        ("W3", 20, 5),
        ("W4", 20, 10),
        ("W5", 25, 5),
    ]

    rows = []

    for name, train_days, test_days in windows:
        test_start = end - pd.Timedelta(days=test_days)
        test_end = end
        test = data[
            (data["timestamp"] >= test_start) &
            (data["timestamp"] <= test_end)
        ].copy()

        for cid, grid, size, mult in CANDIDATES:
            r = simulate(test, grid, size, mult)
            rows.append({
                "window": name,
                "candidate": cid,
                "grid_pct": grid * 100,
                "order_size": size,
                "sell_mult": mult,
                "test_pnl": r["pnl"],
                "test_pnl_day": r["pnl_day"],
                "test_dd": r["dd"],
                "test_trades": r["trades"],
                "test_fees": r["fees"],
                "final_btc": r["final_btc"],
                "buys": r["buys"],
                "sells": r["sells"],
            })

    out = pd.DataFrame(rows)
    ts = pd.Timestamp.now(tz="UTC").strftime("%Y%m%d_%H%M%S")
    csv = BASE / f"v50_fixed_candidates_5windows_{ts}.csv"
    out.to_csv(csv, index=False)

    summary = out.groupby("candidate").agg(
        windows=("window", "count"),
        positive_windows=("test_pnl", lambda s: int((s > 0).sum())),
        total_pnl=("test_pnl", "sum"),
        median_pnl_day=("test_pnl_day", "median"),
        mean_pnl_day=("test_pnl_day", "mean"),
        worst_dd=("test_dd", "min"),
        total_fees=("test_fees", "sum"),
        total_trades=("test_trades", "sum"),
    ).reset_index()

    summary["pass"] = (
        (summary["positive_windows"] >= 4) &
        (summary["median_pnl_day"] > 0) &
        (summary["total_pnl"] > 0) &
        (summary["worst_dd"] > -5.0)
    )

    summary = summary.sort_values(
        ["pass", "positive_windows", "median_pnl_day", "total_pnl"],
        ascending=[False, False, False, False]
    )

    summary_csv = BASE / f"v50_fixed_candidates_summary_{ts}.csv"
    summary.to_csv(summary_csv, index=False)

    print()
    print("=" * 76)
    print("       ADAPTIVE GRID BOT v5.0 - FIXED CANDIDATE VALIDATION")
    print("=" * 76)
    print("NO optimizer selection per window.")
    print("Every candidate is tested across the same unseen windows.")
    print()

    print("WINDOW RESULTS")
    print("-" * 76)
    print(out[[
        "window", "candidate", "grid_pct", "order_size", "sell_mult",
        "test_pnl", "test_pnl_day", "test_dd", "test_trades", "test_fees"
    ]].to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    print()
    print("ROBUSTNESS SUMMARY")
    print("-" * 76)
    print(summary.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    print()
    print("PROPOSED PASS CRITERIA")
    print("-" * 76)
    print("Positive TEST windows >= 4/5")
    print("Median TEST P/L/day > 0")
    print("Total TEST P/L > 0")
    print("Worst TEST DD > -5%")

    print()
    print(f"Detailed CSV : {csv.name}")
    print(f"Summary CSV  : {summary_csv.name}")

    best = summary.iloc[0]
    print()
    print("CURRENT BEST")
    print("-" * 76)
    print(f"Candidate        : {best['candidate']}")
    print(f"Positive windows : {int(best['positive_windows'])}/{int(best['windows'])}")
    print(f"Total P/L        : {best['total_pnl']:+.6f} USDT")
    print(f"Median P/L/day   : {best['median_pnl_day']:+.6f} USDT")
    print(f"Worst DD         : {best['worst_dd']:.4f}%")

    print()
    if bool(best["pass"]):
        print("PASS: candidate meets the current robustness criteria.")
        print("Next step: build v5 Demo Smart Loop.")
    else:
        print("NOT ROBUST: do not deploy .env.v50 yet.")


if __name__ == "__main__":
    main()
