import json
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

CANDIDATES = [
    {"name": "A", "grid": 0.0100, "size": 15.0, "sell_mult": 1.5},
    {"name": "B", "grid": 0.0060, "size": 15.0, "sell_mult": 2.5},
]

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

    # Exact timestamp merge; use only already-known daily ATR.
    h = h.merge(d[["timestamp", "atr30"]], on="timestamp", how="left")
    h["atr30"] = h["atr30"].ffill()

    end = h["timestamp"].max()
    start = end - pd.Timedelta(days=30)
    h = h[h["timestamp"] >= start].reset_index(drop=True)

    if len(h) < 24 * 25:
        raise RuntimeError("Not enough data for 30D walk-forward.")

    return h


def simulate(data, grid, size, sell_mult):
    cash = CAPITAL
    btc = 0.0
    anchor = float(data.iloc[0]["open"])
    equity_curve = []
    trades = 0
    fees_paid = 0.0

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

        # Conservative one-fill-per-candle assumption.
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
                fees_paid += fee
                trades += 1

        elif side == "SELL" and btc > 0:
            qty = min(size / price, btc)
            gross = qty * price
            fee = gross * FEE

            cash += gross - fee
            btc -= qty
            fees_paid += fee
            trades += 1

        equity = cash + btc * close
        equity_curve.append(equity)

        if abs(close - anchor) >= REBUILD_LEVELS * grid * anchor:
            anchor = close

    curve = np.asarray(equity_curve)
    peak = np.maximum.accumulate(curve)
    dd = (curve - peak) / peak

    pnl = float(curve[-1] - CAPITAL)

    return {
        "pnl": pnl,
        "trades": trades,
        "fees": fees_paid,
        "max_dd": float(dd.min() * 100),
        "final_equity": float(curve[-1]),
        "final_btc": btc,
    }


def summarize(label, data, result):
    days = max((data.iloc[-1]["timestamp"] - data.iloc[0]["timestamp"]).total_seconds() / 86400, 1 / 24)
    return {
        "set": label,
        "start": str(data.iloc[0]["timestamp"]),
        "end": str(data.iloc[-1]["timestamp"]),
        "days": days,
        "pnl_usdt": result["pnl"],
        "pnl_per_day": result["pnl"] / days,
        "trades": result["trades"],
        "trades_per_day": result["trades"] / days,
        "fees": result["fees"],
        "max_drawdown_pct": result["max_dd"],
        "final_equity": result["final_equity"],
        "final_btc": result["final_btc"],
    }


def main():
    data = load_data()

    # 20D train / 10D unseen test.
    split = data["timestamp"].min() + pd.Timedelta(days=20)
    train = data[data["timestamp"] < split].copy()
    test = data[data["timestamp"] >= split].copy()

    rows = []

    for c in CANDIDATES:
        tr = simulate(train, c["grid"], c["size"], c["sell_mult"])
        te = simulate(test, c["grid"], c["size"], c["sell_mult"])

        # Buy & hold for each window.
        train_bh = CAPITAL * float(train.iloc[-1]["close"]) / float(train.iloc[0]["open"]) - CAPITAL
        test_bh = CAPITAL * float(test.iloc[-1]["close"]) / float(test.iloc[0]["open"]) - CAPITAL

        a = summarize("TRAIN", train, tr)
        b = summarize("TEST", test, te)

        a.update(candidate=c["name"], grid_pct=c["grid"] * 100, order_size=c["size"], sell_mult=c["sell_mult"], buy_hold_pnl=train_bh, alpha_vs_bh=a["pnl_usdt"] - train_bh)
        b.update(candidate=c["name"], grid_pct=c["grid"] * 100, order_size=c["size"], sell_mult=c["sell_mult"], buy_hold_pnl=test_bh, alpha_vs_bh=b["pnl_usdt"] - test_bh)

        rows.extend([a, b])

    out = pd.DataFrame(rows)
    ts = pd.Timestamp.now(tz="UTC").strftime("%Y%m%d_%H%M%S")
    csv = BASE_DIR / f"v05_walkforward_20d_train_10d_test_{ts}.csv"
    out.to_csv(csv, index=False)

    print()
    print("=" * 76)
    print("       ADAPTIVE GRID BOT v5 - WALK-FORWARD VALIDATION")
    print("=" * 76)
    print(f"Train : {train.iloc[0]['timestamp']} -> {train.iloc[-1]['timestamp']}")
    print(f"Test  : {test.iloc[0]['timestamp']} -> {test.iloc[-1]['timestamp']}")
    print(f"Capital: ${CAPITAL:,.2f} | Fee: {FEE*100:.3f}%/side | Slippage: {SLIPPAGE*100:.3f}%")
    print()
    print(out[[
        "candidate", "set", "grid_pct", "order_size", "sell_mult",
        "pnl_usdt", "pnl_per_day", "trades", "fees",
        "max_drawdown_pct", "buy_hold_pnl", "alpha_vs_bh"
    ]].to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    test_only = out[out["set"] == "TEST"].copy()
    best = test_only.sort_values("pnl_per_day", ascending=False).iloc[0]

    print()
    print("TEST WINNER")
    print("-" * 76)
    print(f"Candidate       : {best['candidate']}")
    print(f"Grid            : {best['grid_pct']:.2f}%")
    print(f"Order size      : ${best['order_size']:.2f}")
    print(f"Bull SELL mult. : {best['sell_mult']:.2f}x")
    print(f"Net P/L         : {best['pnl_usdt']:+.6f} USDT")
    print(f"Net P/L / day   : {best['pnl_per_day']:+.6f} USDT")
    print(f"Max drawdown    : {best['max_drawdown_pct']:.4f}%")
    print(f"vs Buy & Hold   : {best['alpha_vs_bh']:+.6f} USDT")
    print()
    print(f"CSV             : {csv.name}")
    print()
    print("IMPORTANT: This is validation only. No orders are created.")
    print("Do NOT use .env.v50 yet. If TEST is positive and robust,")
    print("next step is build the v5 Demo Smart Loop.")


if __name__ == "__main__":
    main()
