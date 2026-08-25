import pandas as pd
from decimal import Decimal


# ============================================================
# CONFIGURATION
# ============================================================

DATA_FILE_1H = "btc_usdt_1h.csv"
DATA_FILE_1D = "btc_usdt_1d.csv"

INITIAL_CAPITAL = Decimal("100")

MAX_EXPOSURE = Decimal("0.30")

ATR_MULTIPLIER = Decimal("0.30")

GRID_BUY_LEVELS = 5
GRID_SELL_LEVELS = 3

FEE_RATE = Decimal("0.001")       # 0.10%
SLIPPAGE_RATE = Decimal("0.0002") # 0.02%

MIN_TRADE_USDT = Decimal("1.00")


# ============================================================
# POSITION SIZING
# ============================================================

TREND_MULTIPLIERS = {
    "UP": [
        Decimal("0.80"),
        Decimal("1.00"),
        Decimal("1.20"),
        Decimal("1.40"),
        Decimal("1.60"),
    ],

    "SIDEWAY": [
        Decimal("1.00"),
        Decimal("1.00"),
        Decimal("1.00"),
        Decimal("1.00"),
        Decimal("1.00"),
    ],

    "DOWN": [
        Decimal("1.00"),
        Decimal("0.80"),
        Decimal("0.60"),
        Decimal("0.40"),
        Decimal("0.20"),
    ],
}


# ============================================================
# INDICATORS
# ============================================================

def calculate_ema(series, period):

    return series.ewm(
        span=period,
        adjust=False,
    ).mean()


def calculate_true_range(df):

    previous_close = df["close"].shift(1)

    tr1 = df["high"] - df["low"]

    tr2 = (
        df["high"] - previous_close
    ).abs()

    tr3 = (
        df["low"] - previous_close
    ).abs()

    return pd.concat(
        [tr1, tr2, tr3],
        axis=1,
    ).max(axis=1)


def calculate_atr(df, period=30):

    true_range = calculate_true_range(df)

    return true_range.ewm(
        alpha=1 / period,
        adjust=False,
    ).mean()


# ============================================================
# LOAD DATA
# ============================================================

def load_market_data():

    df_1h = pd.read_csv(
        DATA_FILE_1H,
        parse_dates=["timestamp"],
    )

    df_1d = pd.read_csv(
        DATA_FILE_1D,
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
# PREPARE INDICATORS
# ============================================================

def prepare_data():

    df_1h, df_1d = load_market_data()

    # 1H Trend
    df_1h["ema50"] = calculate_ema(
        df_1h["close"],
        50,
    )

    df_1h["ema200"] = calculate_ema(
        df_1h["close"],
        200,
    )

    # Daily ATR
    df_1d["atr30"] = calculate_atr(
        df_1d,
        30,
    )

    # Match latest known daily ATR to every 1H candle.
    #
    # IMPORTANT:
    # We use backward merge so a 1H candle only sees
    # information that was already known at that time.
    #
    merged = pd.merge_asof(
        df_1h.sort_values("timestamp"),
        df_1d[
            [
                "timestamp",
                "atr30",
            ]
        ].sort_values("timestamp"),
        on="timestamp",
        direction="backward",
    )

    return merged


# ============================================================
# TREND
# ============================================================

def determine_trend(row):

    price = Decimal(str(row["close"]))
    ema50 = Decimal(str(row["ema50"]))
    ema200 = Decimal(str(row["ema200"]))

    if price > ema50 and ema50 > ema200:
        return "UP"

    if price < ema50 and ema50 < ema200:
        return "DOWN"

    return "SIDEWAY"


# ============================================================
# PORTFOLIO
# ============================================================

class Portfolio:

    def __init__(self):

        self.cash = INITIAL_CAPITAL

        self.btc = Decimal("0")

        self.realized_pnl = Decimal("0")

        self.total_fees = Decimal("0")

        self.total_buys = 0

        self.total_sells = 0

        self.equity_peak = INITIAL_CAPITAL

        self.max_drawdown = Decimal("0")

        self.trade_log = []

    # --------------------------------------------------------
    # Equity
    # --------------------------------------------------------

    def equity(self, price):

        return (
            self.cash
            + self.btc * price
        )

    # --------------------------------------------------------
    # Exposure
    # --------------------------------------------------------

    def exposure(self, price):

        equity = self.equity(price)

        if equity <= 0:
            return Decimal("0")

        return (
            self.btc * price
        ) / equity

    # --------------------------------------------------------
    # Update drawdown
    # --------------------------------------------------------

    def update_drawdown(self, price):

        current_equity = self.equity(price)

        if current_equity > self.equity_peak:

            self.equity_peak = current_equity

        if self.equity_peak > 0:

            drawdown = (
                self.equity_peak
                - current_equity
            ) / self.equity_peak

            if drawdown > self.max_drawdown:

                self.max_drawdown = drawdown

    # --------------------------------------------------------
    # BUY
    # --------------------------------------------------------

    def buy(
        self,
        price,
        usdt_amount,
        timestamp,
        level,
    ):

        if usdt_amount < MIN_TRADE_USDT:
            return False

        # Slippage: buyer pays slightly more
        execution_price = (
            price
            * (
                Decimal("1")
                + SLIPPAGE_RATE
            )
        )

        fee = (
            usdt_amount
            * FEE_RATE
        )

        total_cost = (
            usdt_amount
            + fee
        )

        if total_cost > self.cash:

            return False

        btc_amount = (
            usdt_amount
            / execution_price
        )

        self.cash -= total_cost

        self.btc += btc_amount

        self.total_fees += fee

        self.total_buys += 1

        self.trade_log.append({
            "timestamp": timestamp,
            "side": "BUY",
            "level": level,
            "price": execution_price,
            "usdt": usdt_amount,
            "btc": btc_amount,
            "fee": fee,
        })

        return True

    # --------------------------------------------------------
    # SELL
    # --------------------------------------------------------

    def sell(
        self,
        price,
        btc_amount,
        timestamp,
        level,
    ):

        if btc_amount <= 0:
            return False

        if btc_amount > self.btc:

            btc_amount = self.btc

        if btc_amount <= 0:
            return False

        # Slippage: seller receives slightly less
        execution_price = (
            price
            * (
                Decimal("1")
                - SLIPPAGE_RATE
            )
        )

        gross_value = (
            btc_amount
            * execution_price
        )

        fee = (
            gross_value
            * FEE_RATE
        )

        net_value = (
            gross_value
            - fee
        )

        self.btc -= btc_amount

        self.cash += net_value

        self.total_fees += fee

        self.total_sells += 1

        self.trade_log.append({
            "timestamp": timestamp,
            "side": "SELL",
            "level": level,
            "price": execution_price,
            "usdt": net_value,
            "btc": btc_amount,
            "fee": fee,
        })

        return True


# ============================================================
# GRID
# ============================================================

def build_grid(
    price,
    grid_distance,
):

    buy_levels = []

    sell_levels = []

    for level in range(
        1,
        GRID_BUY_LEVELS + 1,
    ):

        buy_levels.append({
            "level": -level,
            "price": (
                price
                - grid_distance * level
            ),
        })

    for level in range(
        1,
        GRID_SELL_LEVELS + 1,
    ):

        sell_levels.append({
            "level": level,
            "price": (
                price
                + grid_distance * level
            ),
        })

    return buy_levels, sell_levels


# ============================================================
# POSITION SIZE
# ============================================================

def calculate_grid_sizes(
    equity,
    trend,
):

    max_exposure = (
        equity
        * MAX_EXPOSURE
    )

    base_size = (
        max_exposure
        / Decimal(str(GRID_BUY_LEVELS))
    )

    multipliers = TREND_MULTIPLIERS[
        trend
    ]

    requested = []

    for index, multiplier in enumerate(
        multipliers,
        start=1,
    ):

        size = (
            base_size
            * multiplier
        )

        requested.append({
            "level": -index,
            "size": size,
        })

    # Scale to max exposure
    total_requested = sum(
        item["size"]
        for item in requested
    )

    if total_requested > max_exposure:

        scale = (
            max_exposure
            / total_requested
        )

        for item in requested:

            item["size"] *= scale

    return requested


# ============================================================
# SIMULATION
# ============================================================

def run_backtest(df):

    portfolio = Portfolio()

    active_buys = {}

    active_sells = {}

    previous_trend = None

    grid_center = None

    grid_distance = None

    trend_changes = 0

    grid_rebuilds = 0

    start_time = df.iloc[0]["timestamp"]

    end_time = df.iloc[-1]["timestamp"]

    for _, row in df.iterrows():

        timestamp = row["timestamp"]

        close = Decimal(
            str(row["close"])
        )

        high = Decimal(
            str(row["high"])
        )

        low = Decimal(
            str(row["low"])
        )

        atr30 = row["atr30"]

        # Skip until ATR exists
        if pd.isna(atr30):
            continue

        atr30 = Decimal(
            str(atr30)
        )

        if atr30 <= 0:
            continue

        trend = determine_trend(row)

        # ----------------------------------------------------
        # Rebuild grid when trend changes
        # ----------------------------------------------------

        if (
            previous_trend is None
            or trend != previous_trend
        ):

            trend_changes += 1

            grid_center = close

            grid_distance = (
                atr30
                * ATR_MULTIPLIER
            )

            buy_levels, sell_levels = build_grid(
                grid_center,
                grid_distance,
            )

            active_buys.clear()
            active_sells.clear()

            sizes = calculate_grid_sizes(
                portfolio.equity(close),
                trend,
            )

            size_map = {
                item["level"]: item["size"]
                for item in sizes
            }

            for level in buy_levels:

                level_id = level["level"]

                active_buys[level_id] = {
                    "price": level["price"],
                    "size": size_map.get(
                        level_id,
                        Decimal("0"),
                    ),
                }

            # Sell grid is initially only useful
            # when BTC is already held.
            #
            # We keep sell levels available,
            # but actual sell quantity is determined
            # by current BTC inventory.
            for level in sell_levels:

                active_sells[
                    level["level"]
                ] = {
                    "price": level["price"],
                }

            grid_rebuilds += 1

        previous_trend = trend

        # ----------------------------------------------------
        # BUY FILL
        # ----------------------------------------------------

        filled_buy_levels = []

        for level_id, order in list(
            active_buys.items()
        ):

            order_price = order["price"]

            if low <= order_price:

                current_exposure = (
                    portfolio.exposure(
                        close
                    )
                )

                max_allowed = (
                    Decimal("1")
                    * MAX_EXPOSURE
                )

                if (
                    current_exposure
                    < max_allowed
                ):

                    portfolio.buy(
                        price=order_price,
                        usdt_amount=order["size"],
                        timestamp=timestamp,
                        level=level_id,
                    )

                filled_buy_levels.append(
                    level_id
                )

        for level_id in filled_buy_levels:

            del active_buys[level_id]

        # ----------------------------------------------------
        # SELL FILL
        # ----------------------------------------------------

        filled_sell_levels = []

        for level_id, order in list(
            active_sells.items()
        ):

            order_price = order["price"]

            if high >= order_price:

                if portfolio.btc > 0:

                    # Sell a portion of current BTC
                    #
                    # For V1 we use the nearest
                    # available grid size.
                    target_usdt = (
                        portfolio.equity(close)
                        * MAX_EXPOSURE
                        / Decimal(
                            str(GRID_SELL_LEVELS)
                        )
                    )

                    btc_to_sell = (
                        target_usdt
                        / order_price
                    )

                    portfolio.sell(
                        price=order_price,
                        btc_amount=btc_to_sell,
                        timestamp=timestamp,
                        level=level_id,
                    )

                    filled_sell_levels.append(
                        level_id
                    )

        for level_id in filled_sell_levels:

            del active_sells[level_id]

        # ----------------------------------------------------
        # Refill grid after fills
        # ----------------------------------------------------

        if grid_center is not None:

            # If a BUY was filled, create
            # a SELL one grid above the fill.
            #
            # If SELL was filled, create
            # a BUY one grid below the fill.

            for trade in portfolio.trade_log[-20:]:

                trade_price = trade["price"]

                if trade["side"] == "BUY":

                    sell_price = (
                        trade_price
                        + grid_distance
                    )

                    if not any(
                        abs(
                            item["price"]
                            - sell_price
                        )
                        < Decimal("0.01")
                        for item in active_sells.values()
                    ):

                        active_sells[
                            trade["level"]
                        ] = {
                            "price": sell_price,
                        }

                elif trade["side"] == "SELL":

                    buy_price = (
                        trade_price
                        - grid_distance
                    )

                    if not any(
                        abs(
                            item["price"]
                            - buy_price
                        )
                        < Decimal("0.01")
                        for item in active_buys.values()
                    ):

                        active_buys[
                            trade["level"]
                        ] = {
                            "price": buy_price,
                            "size": (
                                portfolio.equity(close)
                                * MAX_EXPOSURE
                                / Decimal(
                                    str(
                                        GRID_BUY_LEVELS
                                    )
                                )
                            ),
                        }

        # ----------------------------------------------------
        # Risk tracking
        # ----------------------------------------------------

        portfolio.update_drawdown(
            close
        )

    # ========================================================
    # RESULTS
    # ========================================================

    final_price = Decimal(
        str(df.iloc[-1]["close"])
    )

    final_equity = portfolio.equity(
        final_price
    )

    profit = (
        final_equity
        - INITIAL_CAPITAL
    )

    return_percent = (
        profit
        / INITIAL_CAPITAL
        * Decimal("100")
    )

    return {
        "start_time": start_time,
        "end_time": end_time,
        "initial_capital": INITIAL_CAPITAL,
        "final_equity": final_equity,
        "profit": profit,
        "return_percent": return_percent,
        "btc": portfolio.btc,
        "cash": portfolio.cash,
        "realized_pnl": portfolio.realized_pnl,
        "fees": portfolio.total_fees,
        "buys": portfolio.total_buys,
        "sells": portfolio.total_sells,
        "max_drawdown": portfolio.max_drawdown,
        "trend_changes": trend_changes,
        "grid_rebuilds": grid_rebuilds,
        "trades": portfolio.trade_log,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 75)
    print("             ADAPTIVE GRID BOT")
    print("              PAPER TRADER V1")
    print("=" * 75)

    print()
    print("Loading historical data...")

    df = prepare_data()

    print(
        f"1H candles       : {len(df):,}"
    )

    print(
        f"Period           : "
        f"{df['timestamp'].iloc[0]}"
        f" → "
        f"{df['timestamp'].iloc[-1]}"
    )

    print()
    print("Simulation")
    print("-" * 75)

    print(
        f"Initial Capital  : "
        f"{INITIAL_CAPITAL:.2f} USDT"
    )

    print(
        f"Max Exposure     : "
        f"{MAX_EXPOSURE * 100:.0f}%"
    )

    print(
        f"Grid Distance    : "
        f"{ATR_MULTIPLIER} × ATR30D"
    )

    print(
        f"Fee              : "
        f"{FEE_RATE * 100:.3f}%"
    )

    print(
        f"Slippage         : "
        f"{SLIPPAGE_RATE * 100:.3f}%"
    )

    print()
    print("Running backtest...")

    result = run_backtest(
        df
    )

    print()
    print("=" * 75)
    print("                    RESULTS")
    print("=" * 75)

    print()

    print(
        f"Initial Equity    : "
        f"{result['initial_capital']:.2f} USDT"
    )

    print(
        f"Final Equity      : "
        f"{result['final_equity']:.2f} USDT"
    )

    print(
        f"Profit / Loss     : "
        f"{result['profit']:.2f} USDT"
    )

    print(
        f"Return            : "
        f"{result['return_percent']:.2f}%"
    )

    print()

    print(
        f"Cash              : "
        f"{result['cash']:.2f} USDT"
    )

    print(
        f"BTC Position      : "
        f"{result['btc']:.8f} BTC"
    )

    print(
        f"Fees              : "
        f"{result['fees']:.4f} USDT"
    )

    print()

    print(
        f"BUY fills         : "
        f"{result['buys']}"
    )

    print(
        f"SELL fills        : "
        f"{result['sells']}"
    )

    print(
        f"Trend changes     : "
        f"{result['trend_changes']}"
    )

    print(
        f"Grid rebuilds     : "
        f"{result['grid_rebuilds']}"
    )

    print()

    print(
        f"Max Drawdown      : "
        f"{result['max_drawdown'] * 100:.2f}%"
    )

    print()

    print("=" * 75)
    print("                 PAPER TRADING ONLY")
    print("             NO REAL ORDERS WERE SENT")
    print("=" * 75)
    print()


if __name__ == "__main__":
    main()