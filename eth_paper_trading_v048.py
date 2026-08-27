from decimal import Decimal
from dataclasses import dataclass
import pandas as pd
from eth_grid_engine_v048 import FILE_1H, FILE_1D, ATR_MULTIPLIER, GRID_LEVELS_UP, GRID_LEVELS_DOWN, calculate_ema, calculate_atr, determine_trend, build_grid, calculate_position_sizing, evaluate_risk

@dataclass
class PaperState:
    usdt: Decimal
    eth: Decimal
    realized_pnl: Decimal = Decimal('0')
    fees: Decimal = Decimal('0')
    completed_cycles: int = 0

def load_market_data():
    h = pd.read_csv(FILE_1H, parse_dates=["timestamp"])
    d = pd.read_csv(FILE_1D, parse_dates=["timestamp"])
    if len(h) < 200 or len(d) < 31:
        raise RuntimeError("Insufficient historical data")
    h["ema50"] = calculate_ema(h, 50)
    h["ema200"] = calculate_ema(h, 200)
    d["atr30"] = calculate_atr(d, 30)
    return h, d

def run_paper_simulation():
    h, d = load_market_data()
    sizing = calculate_position_sizing()
    state = PaperState(Decimal("1000"), Decimal("0"))
    snapshots = 0
    blocks = 0
    fills = []

    # Deterministic conservative candle-fill model:
    # each candle is processed in chronological order. A BUY level is
    # considered touched when low <= level; a SELL level when high >= level.
    # If both a BUY and SELL are touched in the same candle, we do not
    # assume an intrabar sequence and therefore skip that candle.
    active_buy = None

    for _, row in h.iterrows():
        daily = d[d["timestamp"] <= row["timestamp"]]
        if len(daily) < 31:
            continue

        price = Decimal(str(row["close"]))
        low = Decimal(str(row["low"]))
        high = Decimal(str(row["high"]))
        atr = Decimal(str(daily.iloc[-1]["atr30"]))
        trend = determine_trend(row)
        risk = evaluate_risk(price, atr, trend, sizing)
        if risk["status"] != "PASS":
            blocks += 1
            continue

        distance = atr * Decimal(str(ATR_MULTIPLIER))
        grid = build_grid(price, distance, GRID_LEVELS_UP, GRID_LEVELS_DOWN)
        snapshots += 1

        buys = [Decimal(str(x)) for x in grid.loc[grid["side"] == "BUY", "price"] if low <= Decimal(str(x))]
        sells = [Decimal(str(x)) for x in grid.loc[grid["side"] == "SELL", "price"] if high >= Decimal(str(x))]

        if buys and sells:
            continue

        if buys and active_buy is None:
            fill_price = max(buys)
            qty = Decimal(str(sizing["order_size_usdt"])) / fill_price
            active_buy = {"timestamp": row["timestamp"], "price": fill_price, "qty": qty}
            fills.append({"timestamp": row["timestamp"], "side": "BUY", "price": fill_price, "qty": qty})
            continue

        if sells and active_buy is not None:
            fill_price = min(sells)
            qty = active_buy["qty"]
            gross = (fill_price - active_buy["price"]) * qty
            fee = (fill_price * qty + active_buy["price"] * qty) * Decimal("0.001")
            net = gross - fee
            state.realized_pnl += net
            state.fees += fee
            state.completed_cycles += 1
            fills.append({"timestamp": row["timestamp"], "side": "SELL", "price": fill_price, "qty": qty, "pnl": net})
            active_buy = None

    if active_buy is not None:
        state.eth = active_buy["qty"]

    return state, snapshots, blocks, fills

def main():
    print("=" * 76)
    print("ETH-USDT ADAPTIVE GRID BOT v4.8 | PAPER TRADING")
    print("HISTORICAL / NO ORDERS")
    print("=" * 76)
    state, snapshots, blocks, fills = run_paper_simulation()
    print(f"Grid snapshots   : {snapshots}")
    print(f"Risk blocks      : {blocks}")
    print(f"Paper fills      : {len(fills)}")
    print(f"Completed cycles : {state.completed_cycles}")
    print(f"Realized P/L     : {state.realized_pnl:.6f} USDT")
    print(f"Fees             : {state.fees:.6f} USDT")
    print(f"ETH inventory    : {state.eth:.8f} ETH")
    print("Exchange writes  : NONE")


if __name__ == "__main__":
    main()

if __name__ == '__main__':
    main()
