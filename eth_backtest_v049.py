from decimal import Decimal
import pandas as pd

from eth_adaptive_grid_v049_demo_smart_loop import (
    BUY_LEVELS,
    SELL_LEVELS,
    ATR_PERIOD,
    GRID_LOW,
    GRID_NORMAL,
    GRID_HIGH,
    GRID_EXTREME,
    LOW_THRESHOLD,
    NORMAL_THRESHOLD,
    HIGH_THRESHOLD,
    REBUILD_AFTER_GRID_STEPS,
    build_grid,
    determine_regime,
)

INITIAL_CAPITAL = Decimal("1000.00")
ORDER_SIZE_USDT = Decimal("5.00")
FEE_RATE = Decimal("0.001")
MAX_EXPOSURE_USDT = Decimal("500.00")
MAX_INVENTORY_USDT = Decimal("1050.00")


def D(value):
    return Decimal(str(value))


def load_data():
    h = pd.read_csv("eth_usdt_1h.csv", parse_dates=["timestamp"])
    d = pd.read_csv("eth_usdt_1d.csv", parse_dates=["timestamp"])
    if len(h) < 200 or len(d) < ATR_PERIOD + 1:
        raise RuntimeError("Insufficient ETH history for v4.9 backtest")

    previous_close = d["close"].shift(1)
    tr = pd.concat(
        [
            d["high"] - d["low"],
            (d["high"] - previous_close).abs(),
            (d["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    d["atr30"] = tr.ewm(alpha=1 / ATR_PERIOD, adjust=False).mean()
    return h, d


def run_backtest():
    h, d = load_data()
    cash = INITIAL_CAPITAL
    eth = Decimal("0")
    realized = Decimal("0")
    fees = Decimal("0")
    peak_equity = INITIAL_CAPITAL
    max_drawdown = Decimal("0")
    fills = []
    cycles = []
    regime_counts = {}
    rebuilds = 0
    risk_blocks = 0

    anchor = None
    previous_regime = None
    active_buys = {}
    active_sells = {}
    cost_basis = Decimal("0")

    for i in range(1, len(h)):
        row = h.iloc[i]
        prev = h.iloc[i - 1]
        prior_days = d[d["timestamp"] < row["timestamp"]]
        if len(prior_days) < ATR_PERIOD:
            continue

        price = D(prev["close"])
        atr = D(prior_days.iloc[-1]["atr30"])
        if price <= 0 or atr <= 0:
            risk_blocks += 1
            continue

        atr_percent = atr / price
        regime, grid_percent = determine_regime(atr_percent)
        regime_counts[regime] = regime_counts.get(regime, 0) + 1

        step = price * grid_percent
        rebuild = anchor is None
        if anchor is not None:
            if previous_regime and previous_regime != regime:
                rebuild = True
            elif step > 0 and abs(price - anchor) >= anchor * grid_percent * REBUILD_AFTER_GRID_STEPS:
                rebuild = True

        if rebuild:
            anchor = price
            active_buys = {}
            active_sells = {}
            rebuilds += 1
            grid = build_grid(anchor, grid_percent, _BacktestManager())
            for item in grid:
                if item["side"] == "buy":
                    active_buys[item["level"]] = D(item["price"])
                else:
                    active_sells[item["level"]] = D(item["price"])
        previous_regime = regime

        low = D(row["low"])
        high = D(row["high"])

        # Conservative OHLC rule: if both directions are touched, do not
        # assume an intrabar sequence. Preserve the grid for the next candle.
        touched_buys = [x for x in active_buys.items() if low <= x[1]]
        touched_sells = [x for x in active_sells.items() if high >= x[1]]
        if touched_buys and touched_sells:
            touched_buys = []
            touched_sells = []

        # One fill per candle. This keeps the historical model conservative.
        if touched_buys:
            level, fill_price = max(touched_buys, key=lambda x: x[1])
            notional = ORDER_SIZE_USDT
            fee = notional * FEE_RATE
            inventory_value = eth * price
            if cash >= notional + fee and inventory_value + notional <= MAX_INVENTORY_USDT:
                qty = notional / fill_price
                cash -= notional + fee
                eth += qty
                cost_basis += notional
                fees += fee
                fills.append((row["timestamp"], "BUY", fill_price, qty, Decimal("0")))
                active_buys.pop(level, None)
                # The corresponding sell level is placed one grid step above.
                sell_level = abs(level)
                if sell_level <= SELL_LEVELS:
                    active_sells[sell_level] = anchor * (D("1") + grid_percent * sell_level)
            else:
                risk_blocks += 1

        elif touched_sells and eth > 0:
            level, fill_price = min(touched_sells, key=lambda x: x[1])
            qty = min(eth, ORDER_SIZE_USDT / anchor)
            gross = (fill_price * qty) - (cost_basis * (qty / eth) if eth > 0 else Decimal("0"))
            fee = fill_price * qty * FEE_RATE
            cash += fill_price * qty - fee
            eth -= qty
            allocated_cost = cost_basis * (qty / (eth + qty)) if (eth + qty) > 0 else Decimal("0")
            cost_basis -= allocated_cost
            net = gross - fee
            realized += net
            fees += fee
            cycles.append(net)
            fills.append((row["timestamp"], "SELL", fill_price, qty, net))
            active_sells.pop(level, None)
            buy_level = -abs(level)
            active_buys[buy_level] = anchor * (D("1") - grid_percent * abs(level))

        equity = cash + eth * D(row["close"])
        peak_equity = max(peak_equity, equity)
        max_drawdown = max(max_drawdown, peak_equity - equity)

    last_price = D(h.iloc[-1]["close"])
    equity = cash + eth * last_price
    unrealized = equity - cash - cost_basis
    wins = sum(1 for x in cycles if x > 0)
    losses = sum(1 for x in cycles if x < 0)
    gross_profit = sum((x for x in cycles if x > 0), Decimal("0"))
    gross_loss = -sum((x for x in cycles if x < 0), Decimal("0"))

    return {
        "candles": len(h),
        "fills": len(fills),
        "cycles": len(cycles),
        "wins": wins,
        "losses": losses,
        "win_rate": D(wins) / D(len(cycles)) * 100 if cycles else Decimal("0"),
        "realized": realized,
        "unrealized": unrealized,
        "equity": equity,
        "cash": cash,
        "mark_price": last_price,
        "cost_basis": cost_basis,
        "cash": cash,
        "mark_price": last_price,
        "cost_basis": cost_basis,
        "fees": fees,
        "profit_factor": gross_profit / gross_loss if gross_loss else Decimal("Infinity"),
        "avg_cycle": realized / D(len(cycles)) if cycles else Decimal("0"),
        "max_drawdown": max_drawdown,
        "inventory": eth,
        "rebuilds": rebuilds,
        "risk_blocks": risk_blocks,
        "regimes": regime_counts,
    }


class _BacktestManager:
    def normalize_price(self, value):
        return D(value).quantize(Decimal("0.01"))


def main():
    r = run_backtest()
    print("=" * 76)
    print("ETH-USDT ADAPTIVE GRID BOT v4.9 | BACKTEST")
    print("HISTORICAL / NO ORDERS / CONSERVATIVE OHLC MODEL")
    print("=" * 76)
    print(f"Candles          : {r['candles']}")
    print(f"Fills            : {r['fills']}")
    print(f"Completed cycles : {r['cycles']}")
    print(f"Winning cycles   : {r['wins']}")
    print(f"Losing cycles    : {r['losses']}")
    print(f"Win rate         : {r['win_rate']:.2f}%")
    print(f"Realized P/L     : {r['realized']:.6f} USDT")
    print(f"Unrealized P/L   : {r['unrealized']:.6f} USDT")
    print(f"Equity           : {r['equity']:.6f} USDT")
    print(f"Fees             : {r['fees']:.6f} USDT")
    print(f"Profit factor    : {r['profit_factor']:.4f}")
    print(f"Avg cycle P/L    : {r['avg_cycle']:.6f} USDT")
    print(f"Max drawdown     : {r['max_drawdown']:.6f} USDT")
    print(f"ETH inventory    : {r['inventory']:.8f} ETH")
    print(f"Grid rebuilds    : {r['rebuilds']}")
    print(f"Risk blocks      : {r['risk_blocks']}")
    print(f"Regimes          : {r['regimes']}")
    print("Exchange writes  : NONE")


if __name__ == "__main__":
    main()
