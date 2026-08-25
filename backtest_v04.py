import pandas as pd
from decimal import Decimal


# ============================================================
# ADAPTIVE GRID BOT v4 - FULL BACKTEST
# v2 TREND ENGINE + v4 ADAPTIVE GRID + RISK CONTROL
# ============================================================

FILE_1H = "btc_usdt_1h.csv"
FILE_1D = "btc_usdt_1d.csv"

# Strategy
INITIAL_CAPITAL = Decimal("1000")
MAX_EXPOSURE_USDT = Decimal("500")
ORDER_SIZE_USDT = Decimal("5")

BUY_LEVELS = 10
SELL_LEVELS = 10
MAX_GRID_ORDERS = BUY_LEVELS + SELL_LEVELS

# v2 trend confirmation
CONFIRM_CANDLES = 6

# Daily ATR
ATR_PERIOD = 30

# v4 volatility regimes
LOW_THRESHOLD = Decimal("0.01")
NORMAL_THRESHOLD = Decimal("0.02")
HIGH_THRESHOLD = Decimal("0.03")

GRID_LOW = Decimal("0.0005")       # 0.05%
GRID_NORMAL = Decimal("0.0010")    # 0.10%
GRID_HIGH = Decimal("0.0020")      # 0.20%
GRID_EXTREME = Decimal("0.0030")   # 0.30%

# Execution
FEE_RATE = Decimal("0.001")        # 0.10%
SLIPPAGE_RATE = Decimal("0.0002")  # 0.02%


def D(value):
    return Decimal(str(value))


# ============================================================
# DATA
# ============================================================

def load_data():
    df_1h = pd.read_csv(FILE_1H, parse_dates=["timestamp"])
    df_1d = pd.read_csv(FILE_1D, parse_dates=["timestamp"])

    df_1h = df_1h.sort_values("timestamp").reset_index(drop=True)
    df_1d = df_1d.sort_values("timestamp").reset_index(drop=True)

    return df_1h, df_1d


# ============================================================
# INDICATORS - PRESERVE V2
# ============================================================

def prepare_data(df_1h, df_1d):
    df_1h = df_1h.copy()
    df_1d = df_1d.copy()

    df_1h["ema50"] = df_1h["close"].ewm(
        span=50, adjust=False
    ).mean()

    df_1h["ema200"] = df_1h["close"].ewm(
        span=200, adjust=False
    ).mean()

    df_1h["ema50_slope"] = df_1h["ema50"].diff()

    previous_close = df_1d["close"].shift(1)

    tr1 = df_1d["high"] - df_1d["low"]
    tr2 = (df_1d["high"] - previous_close).abs()
    tr3 = (df_1d["low"] - previous_close).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    df_1d["atr30"] = true_range.ewm(
        alpha=1 / ATR_PERIOD,
        adjust=False
    ).mean()

    # Backward merge prevents future daily ATR leakage.
    df = pd.merge_asof(
        df_1h.sort_values("timestamp"),
        df_1d[["timestamp", "atr30"]].sort_values("timestamp"),
        on="timestamp",
        direction="backward",
    )

    return df


# ============================================================
# V2 TREND ENGINE
# ============================================================

def raw_signal(row):
    price = row["close"]
    ema50 = row["ema50"]
    ema200 = row["ema200"]
    slope = row["ema50_slope"]

    if price > ema50 and ema50 > ema200 and slope > 0:
        return "UP"

    if price < ema50 and ema50 < ema200 and slope < 0:
        return "DOWN"

    return "SIDEWAY"


class TrendEngine:
    def __init__(self):
        self.current = "SIDEWAY"
        self.candidate = None
        self.candidate_count = 0
        self.changes = 0

    def update(self, signal):
        if signal == self.current:
            self.candidate = None
            self.candidate_count = 0
            return self.current, False

        if signal != self.candidate:
            self.candidate = signal
            self.candidate_count = 1
            return self.current, False

        self.candidate_count += 1

        if self.candidate_count >= CONFIRM_CANDLES:
            old = self.current
            self.current = self.candidate
            self.candidate = None
            self.candidate_count = 0
            self.changes += 1
            return self.current, True

        return self.current, False


# ============================================================
# V4 VOLATILITY REGIME
# ============================================================

def determine_regime(atr, price):
    atr_percent = atr / price

    if atr_percent < LOW_THRESHOLD:
        return "LOW", GRID_LOW, atr_percent

    if atr_percent < NORMAL_THRESHOLD:
        return "NORMAL", GRID_NORMAL, atr_percent

    if atr_percent < HIGH_THRESHOLD:
        return "HIGH", GRID_HIGH, atr_percent

    return "EXTREME", GRID_EXTREME, atr_percent


# ============================================================
# GRID
# ============================================================

def build_grid(center, grid_percent):
    buys = []
    sells = []

    for level in range(1, BUY_LEVELS + 1):
        buys.append({
            "level": -level,
            "price": center * (
                D("1") - grid_percent * level
            ),
            "size": ORDER_SIZE_USDT,
        })

    for level in range(1, SELL_LEVELS + 1):
        sells.append({
            "level": level,
            "price": center * (
                D("1") + grid_percent * level
            ),
        })

    return buys, sells


# ============================================================
# BACKTEST
# ============================================================

def run_backtest(df):
    cash = INITIAL_CAPITAL
    btc = Decimal("0")

    peak = INITIAL_CAPITAL
    max_drawdown = Decimal("0")
    max_exposure = Decimal("0")
    fees = Decimal("0")

    buys = 0
    sells = 0

    trend_engine = TrendEngine()

    buy_orders = []
    sell_orders = []

    grid_percent = None
    regime = "SIDEWAY"

    regime_changes = 0
    grid_rebuilds = 0

    equity_curve = []
    regime_log = []
    trade_log = []

    for _, row in df.iterrows():
        if pd.isna(row["atr30"]):
            continue

        timestamp = row["timestamp"]
        high = D(row["high"])
        low = D(row["low"])
        close = D(row["close"])
        atr = D(row["atr30"])

        if atr <= 0 or close <= 0:
            continue

        signal = raw_signal(row)
        trend, trend_changed = trend_engine.update(signal)

        new_regime, new_grid_percent, atr_percent = determine_regime(
            atr, close
        )

        # Rebuild when the confirmed trend changes OR the
        # volatility regime changes. Initial build also happens here.
        should_rebuild = (
            grid_percent is None
            or trend_changed
            or new_regime != regime
        )

        if should_rebuild:
            if grid_percent is not None and new_regime != regime:
                regime_changes += 1

            regime = new_regime
            grid_percent = new_grid_percent

            buy_orders, sell_orders = build_grid(
                close,
                grid_percent
            )

            grid_rebuilds += 1

            regime_log.append({
                "timestamp": timestamp,
                "trend": trend,
                "regime": regime,
                "atr_percent": float(atr_percent * 100),
                "grid_percent": float(grid_percent * 100),
                "price": float(close),
            })

        # Snapshot the orders that existed at the START of this candle.
        # Replacement orders created by a fill cannot fill again in the
        # same candle. This avoids same-candle cascade/look-ahead effects.
        buy_snapshot = list(buy_orders)
        sell_snapshot = list(sell_orders)

        remaining_buys = []
        filled_buys = []

        for order in buy_snapshot:
            order_price = D(order["price"])

            max_exposure_value = (
                (cash + btc * close) * MAX_EXPOSURE_USDT
                / INITIAL_CAPITAL
            )

            current_exposure = btc * close
            available = max_exposure_value - current_exposure

            if low <= order_price and available > 0:
                size = min(
                    D(order["size"]),
                    available,
                    cash / (D("1") + FEE_RATE),
                )

                if size >= D("5"):
                    execution_price = order_price * (
                        D("1") + SLIPPAGE_RATE
                    )

                    fee = size * FEE_RATE
                    cost = size + fee

                    if cost <= cash:
                        bought = size / execution_price
                        btc += bought
                        cash -= cost
                        fees += fee
                        buys += 1

                        filled_buys.append(order)

                        trade_log.append({
                            "timestamp": timestamp,
                            "side": "BUY",
                            "level": order["level"],
                            "price": float(execution_price),
                            "usdt": float(size),
                            "fee": float(fee),
                            "regime": regime,
                            "trend": trend,
                        })
                        continue

            remaining_buys.append(order)

        # Keep any orders not filled from the snapshot, then add
        # replacements after all BUY fills have been evaluated.
        buy_orders = remaining_buys

        for order in filled_buys:
            replacement_price = D(order["price"]) * (
                D("1") + grid_percent
            )

            buy_orders.append({
                "level": order["level"],
                "price": replacement_price,
                "size": ORDER_SIZE_USDT,
            })

        remaining_sells = []
        filled_sells = []

        for order in sell_snapshot:
            order_price = D(order["price"])

            if high >= order_price and btc > 0:
                # Each SELL attempts to realize one grid-sized amount.
                target_value = min(
                    ORDER_SIZE_USDT,
                    btc * order_price,
                )

                execution_price = order_price * (
                    D("1") - SLIPPAGE_RATE
                )

                sell_btc = min(
                    target_value / execution_price,
                    btc,
                )

                if sell_btc > 0:
                    gross = sell_btc * execution_price
                    fee = gross * FEE_RATE
                    net = gross - fee

                    btc -= sell_btc
                    cash += net
                    fees += fee
                    sells += 1

                    filled_sells.append(order)

                    trade_log.append({
                        "timestamp": timestamp,
                        "side": "SELL",
                        "level": order["level"],
                        "price": float(execution_price),
                        "usdt": float(net),
                        "fee": float(fee),
                        "regime": regime,
                        "trend": trend,
                    })
                    continue

            remaining_sells.append(order)

        sell_orders = remaining_sells

        for order in filled_sells:
            replacement_price = D(order["price"]) * (
                D("1") - grid_percent
            )

            sell_orders.append({
                "level": order["level"],
                "price": replacement_price,
                "size": ORDER_SIZE_USDT,
            })

        # Equity / risk
        equity = cash + btc * close
        exposure = btc * close

        max_exposure = max(
            max_exposure,
            exposure
        )

        if equity > peak:
            peak = equity

        if peak > 0:
            drawdown = (peak - equity) / peak
            max_drawdown = max(max_drawdown, drawdown)

        equity_curve.append({
            "timestamp": timestamp,
            "equity": float(equity),
            "cash": float(cash),
            "btc": float(btc),
            "exposure": float(exposure),
            "drawdown_pct": float(
                (drawdown * 100) if peak > 0 else 0
            ),
            "trend": trend,
            "regime": regime,
            "grid_percent": float(grid_percent * 100),
        })

    curve = pd.DataFrame(equity_curve)

    if curve.empty:
        raise RuntimeError("No valid candles available for backtest")

    final_equity = D(curve.iloc[-1]["equity"])
    profit = final_equity - INITIAL_CAPITAL
    return_pct = profit / INITIAL_CAPITAL * D("100")

    return {
        "initial_equity": INITIAL_CAPITAL,
        "final_equity": final_equity,
        "profit": profit,
        "return_pct": return_pct,
        "max_drawdown": max_drawdown,
        "fees": fees,
        "buys": buys,
        "sells": sells,
        "trend_changes": trend_engine.changes,
        "regime_changes": regime_changes,
        "grid_rebuilds": grid_rebuilds,
        "max_exposure": max_exposure,
        "curve": curve,
        "regime_log": pd.DataFrame(regime_log),
        "trade_log": pd.DataFrame(trade_log),
    }


# ============================================================
# MAIN
# ============================================================

def main():
    print()
    print("=" * 78)
    print("             ADAPTIVE GRID BOT v4")
    print("        FULL BACKTEST: V2 + V4 ENGINE")
    print("=" * 78)

    print()
    print("Loading ALL available historical data...")

    df_1h, df_1d = load_data()

    print(f"1H candles         : {len(df_1h):,}")
    print(f"1D candles         : {len(df_1d):,}")
    print(
        f"1H period          : "
        f"{df_1h['timestamp'].iloc[0]} -> "
        f"{df_1h['timestamp'].iloc[-1]}"
    )

    df = prepare_data(df_1h, df_1d)

    print()
    print("=" * 78)
    print("BACKTEST CONFIGURATION")
    print("=" * 78)

    print(f"Initial Capital    : {INITIAL_CAPITAL:.2f} USDT")
    print(f"Max Exposure       : {MAX_EXPOSURE_USDT:.2f} USDT")
    print(f"Order Size         : {ORDER_SIZE_USDT:.2f} USDT")
    print(f"Grid Levels        : {BUY_LEVELS} BUY / {SELL_LEVELS} SELL")
    print(f"Trend Confirmation : {CONFIRM_CANDLES} candles")
    print(f"ATR Period         : {ATR_PERIOD}D")
    print(f"Fee                : {FEE_RATE * 100:.3f}%")
    print(f"Slippage           : {SLIPPAGE_RATE * 100:.3f}%")

    print()
    print("Running FULL v4 backtest...")

    result = run_backtest(df)

    print()
    print("=" * 78)
    print("                         V4 RESULTS")
    print("=" * 78)

    print()
    print(f"Initial Equity     : {result['initial_equity']:.2f} USDT")
    print(f"Final Equity       : {result['final_equity']:.2f} USDT")
    print(f"Profit / Loss      : {result['profit']:.2f} USDT")
    print(f"Return             : {result['return_pct']:.2f}%")

    print()
    print(f"Max Drawdown       : {result['max_drawdown'] * 100:.2f}%")
    print(f"Max Exposure       : {result['max_exposure']:.2f} USDT")
    print(f"Fees               : {result['fees']:.4f} USDT")

    print()
    print(f"BUY fills          : {result['buys']}")
    print(f"SELL fills         : {result['sells']}")
    print(f"Trend changes      : {result['trend_changes']}")
    print(f"Regime changes     : {result['regime_changes']}")
    print(f"Grid rebuilds      : {result['grid_rebuilds']}")

    curve_file = "backtest_v04_equity.csv"
    regime_file = "backtest_v04_regimes.csv"
    trade_file = "backtest_v04_trades.csv"

    result["curve"].to_csv(curve_file, index=False)
    result["regime_log"].to_csv(regime_file, index=False)
    result["trade_log"].to_csv(trade_file, index=False)

    print()
    print("Saved:")
    print(f"  {curve_file}")
    print(f"  {regime_file}")
    print(f"  {trade_file}")

    print()
    print("=" * 78)
    print("                 V4 BACKTEST COMPLETE")
    print("=" * 78)
    print()


if __name__ == "__main__":
    main()
