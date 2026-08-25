import pandas as pd
from decimal import Decimal


# ============================================================
# CONFIG
# ============================================================

FILE_1H = "btc_usdt_1h.csv"
FILE_1D = "btc_usdt_1d.csv"

INITIAL_CAPITAL = Decimal("100")

MAX_EXPOSURE = Decimal("0.30")
ATR_MULTIPLIER = Decimal("0.30")

FEE_RATE = Decimal("0.001")
SLIPPAGE_RATE = Decimal("0.0002")

GRID_BUY_LEVELS = 5
GRID_SELL_LEVELS = 3

# V2
CONFIRM_CANDLES = 6


# ============================================================
# DATA
# ============================================================

def load_data():

    df_1h = pd.read_csv(
        FILE_1H,
        parse_dates=["timestamp"],
    )

    df_1d = pd.read_csv(
        FILE_1D,
        parse_dates=["timestamp"],
    )

    df_1h = df_1h.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    df_1d = df_1d.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    return df_1h, df_1d


# ============================================================
# INDICATORS
# ============================================================

def prepare_data(df_1h, df_1d):

    df_1h["ema50"] = (
        df_1h["close"]
        .ewm(
            span=50,
            adjust=False,
        )
        .mean()
    )

    df_1h["ema200"] = (
        df_1h["close"]
        .ewm(
            span=200,
            adjust=False,
        )
        .mean()
    )

    # EMA slope
    df_1h["ema50_slope"] = (
        df_1h["ema50"]
        .diff()
    )

    # Daily ATR30
    previous_close = (
        df_1d["close"].shift(1)
    )

    tr1 = (
        df_1d["high"]
        - df_1d["low"]
    )

    tr2 = (
        df_1d["high"]
        - previous_close
    ).abs()

    tr3 = (
        df_1d["low"]
        - previous_close
    ).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1,
    ).max(axis=1)

    df_1d["atr30"] = (
        true_range
        .ewm(
            alpha=1 / 30,
            adjust=False,
        )
        .mean()
    )

    df = pd.merge_asof(
        df_1h,
        df_1d[
            [
                "timestamp",
                "atr30",
            ]
        ],
        on="timestamp",
        direction="backward",
    )

    return df


# ============================================================
# RAW TREND SIGNAL
# ============================================================

def raw_signal(row):

    price = row["close"]
    ema50 = row["ema50"]
    ema200 = row["ema200"]
    slope = row["ema50_slope"]

    if (
        price > ema50
        and ema50 > ema200
        and slope > 0
    ):
        return "UP"

    if (
        price < ema50
        and ema50 < ema200
        and slope < 0
    ):
        return "DOWN"

    return "SIDEWAY"


# ============================================================
# CONFIRMED TREND
# ============================================================

class TrendEngine:

    def __init__(self):

        self.current = "SIDEWAY"

        self.candidate = None

        self.candidate_count = 0

        self.changes = 0

    def update(self, signal):

        # Same as current regime
        if signal == self.current:

            self.candidate = None
            self.candidate_count = 0

            return self.current, False

        # New candidate
        if signal != self.candidate:

            self.candidate = signal
            self.candidate_count = 1

            return self.current, False

        # Candidate continues
        self.candidate_count += 1

        # Confirm
        if (
            self.candidate_count
            >= CONFIRM_CANDLES
        ):

            old = self.current

            self.current = self.candidate

            self.candidate = None

            self.candidate_count = 0

            self.changes += 1

            return self.current, True

        return self.current, False


# ============================================================
# GRID
# ============================================================

def build_grid(
    center,
    distance,
):

    buys = []

    sells = []

    for level in range(
        1,
        GRID_BUY_LEVELS + 1,
    ):

        buys.append(
            center
            - distance * level
        )

    for level in range(
        1,
        GRID_SELL_LEVELS + 1,
    ):

        sells.append(
            center
            + distance * level
        )

    return buys, sells


# ============================================================
# BACKTEST
# ============================================================

def run_backtest(df):

    cash = INITIAL_CAPITAL

    btc = Decimal("0")

    peak = INITIAL_CAPITAL

    max_drawdown = Decimal("0")

    fees = Decimal("0")

    buys = 0
    sells = 0

    trend_engine = TrendEngine()

    buy_orders = []

    sell_orders = []

    grid_distance = None

    equity_curve = []

    for _, row in df.iterrows():

        if pd.isna(row["atr30"]):
            continue

        timestamp = row["timestamp"]

        high = Decimal(
            str(row["high"])
        )

        low = Decimal(
            str(row["low"])
        )

        close = Decimal(
            str(row["close"])
        )

        atr30 = Decimal(
            str(row["atr30"])
        )

        signal = raw_signal(row)

        trend, changed = (
            trend_engine.update(signal)
        )

        # ----------------------------------------------------
        # Rebuild only after confirmed trend
        # ----------------------------------------------------

        if (
            changed
            or grid_distance is None
        ):

            grid_distance = (
                atr30
                * ATR_MULTIPLIER
            )

            buy_orders, sell_orders = (
                build_grid(
                    close,
                    grid_distance,
                )
            )

        # ----------------------------------------------------
        # BUY
        # ----------------------------------------------------

        remaining_buys = []

        for order_price in buy_orders:

            max_exposure_value = (
                (
                    cash
                    + btc * close
                )
                * MAX_EXPOSURE
            )

            current_exposure = (
                btc * close
            )

            available = (
                max_exposure_value
                - current_exposure
            )

            if (
                low <= order_price
                and available > 0
            ):

                size = (
                    available
                    / Decimal(
                        str(
                            GRID_BUY_LEVELS
                        )
                    )
                )

                if size >= Decimal("1"):

                    execution_price = (
                        order_price
                        * (
                            Decimal("1")
                            + SLIPPAGE_RATE
                        )
                    )

                    fee = (
                        size
                        * FEE_RATE
                    )

                    cost = (
                        size
                        + fee
                    )

                    if cost <= cash:

                        bought = (
                            size
                            / execution_price
                        )

                        btc += bought

                        cash -= cost

                        fees += fee

                        buys += 1

                        # Create sell one grid above
                        sell_orders.append(
                            execution_price
                            + grid_distance
                        )

                        continue

            remaining_buys.append(
                order_price
            )

        buy_orders = remaining_buys

        # ----------------------------------------------------
        # SELL
        # ----------------------------------------------------

        remaining_sells = []

        for order_price in sell_orders:

            if (
                high >= order_price
                and btc > 0
            ):

                target_value = (
                    (
                        cash
                        + btc * close
                    )
                    * MAX_EXPOSURE
                    / Decimal(
                        str(
                            GRID_SELL_LEVELS
                        )
                    )
                )

                execution_price = (
                    order_price
                    * (
                        Decimal("1")
                        - SLIPPAGE_RATE
                    )
                )

                sell_btc = (
                    target_value
                    / execution_price
                )

                sell_btc = min(
                    sell_btc,
                    btc,
                )

                if sell_btc > 0:

                    gross = (
                        sell_btc
                        * execution_price
                    )

                    fee = (
                        gross
                        * FEE_RATE
                    )

                    net = (
                        gross
                        - fee
                    )

                    btc -= sell_btc

                    cash += net

                    fees += fee

                    sells += 1

                    # Create buy one grid below
                    buy_orders.append(
                        execution_price
                        - grid_distance
                    )

                    continue

            remaining_sells.append(
                order_price
            )

        sell_orders = remaining_sells

        # ----------------------------------------------------
        # EQUITY
        # ----------------------------------------------------

        equity = (
            cash
            + btc * close
        )

        if equity > peak:

            peak = equity

        if peak > 0:

            drawdown = (
                peak - equity
            ) / peak

            if drawdown > max_drawdown:

                max_drawdown = drawdown

        equity_curve.append({
            "timestamp": timestamp,
            "equity": float(equity),
            "btc": float(btc),
            "cash": float(cash),
            "trend": trend,
        })

    curve = pd.DataFrame(
        equity_curve
    )

    final_equity = Decimal(
        str(
            curve.iloc[-1]["equity"]
        )
    )

    profit = (
        final_equity
        - INITIAL_CAPITAL
    )

    return_pct = (
        profit
        / INITIAL_CAPITAL
        * Decimal("100")
    )

    return {
        "final_equity": final_equity,
        "profit": profit,
        "return_pct": return_pct,
        "max_drawdown": max_drawdown,
        "fees": fees,
        "buys": buys,
        "sells": sells,
        "trend_changes":
            trend_engine.changes,
        "curve": curve,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 75)
    print("          ADAPTIVE GRID BOT - V2")
    print("          TREND CONFIRMATION")
    print("=" * 75)

    print()
    print(
        f"Confirmation     : "
        f"{CONFIRM_CANDLES} candles"
    )

    print(
        f"Grid             : "
        f"{ATR_MULTIPLIER} × ATR30D"
    )

    print(
        f"Initial Capital  : "
        f"{INITIAL_CAPITAL} USDT"
    )

    print()
    print("Loading data...")

    df_1h, df_1d = load_data()

    df = prepare_data(
        df_1h,
        df_1d,
    )

    print(
        f"Candles          : "
        f"{len(df):,}"
    )

    print()
    print("Running V2 backtest...")

    result = run_backtest(
        df
    )

    print()
    print("=" * 75)
    print("                         V2 RESULTS")
    print("=" * 75)

    print()

    print(
        f"Initial Equity   : "
        f"{INITIAL_CAPITAL:.2f}"
    )

    print(
        f"Final Equity     : "
        f"{result['final_equity']:.2f}"
    )

    print(
        f"Profit / Loss    : "
        f"{result['profit']:.2f}"
    )

    print(
        f"Return           : "
        f"{result['return_pct']:.2f}%"
    )

    print()

    print(
        f"Max Drawdown     : "
        f"{result['max_drawdown'] * 100:.2f}%"
    )

    print(
        f"Fees             : "
        f"{result['fees']:.4f}"
    )

    print()

    print(
        f"BUY fills        : "
        f"{result['buys']}"
    )

    print(
        f"SELL fills       : "
        f"{result['sells']}"
    )

    print(
        f"Trend changes    : "
        f"{result['trend_changes']}"
    )

    result["curve"].to_csv(
        "backtest_v2_equity.csv",
        index=False,
    )

    print()
    print(
        "Saved: backtest_v2_equity.csv"
    )

    print()
    print("=" * 75)
    print("                   V2 TEST COMPLETE")
    print("=" * 75)
    print()


if __name__ == "__main__":
    main()