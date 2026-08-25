import pandas as pd
from decimal import Decimal


# ============================================================
# ADAPTIVE GRID BOT v4.0
# PAPER TRADING ENGINE
# ============================================================

DATA_FILE_1H = "btc_usdt_1h.csv"
DATA_FILE_1D = "btc_usdt_1d.csv"


# ============================================================
# CAPITAL / RISK
# ============================================================

INITIAL_CAPITAL = Decimal("1000")

MAX_EXPOSURE_USDT = Decimal("500")

ORDER_SIZE_USDT = Decimal("5")

MAX_GRID_ORDERS = 20


# ============================================================
# GRID
# ============================================================

BUY_LEVELS = 10
SELL_LEVELS = 10

ATR_PERIOD = 30


# ============================================================
# VOLATILITY REGIME
# ============================================================

LOW_THRESHOLD = Decimal("0.01")
NORMAL_THRESHOLD = Decimal("0.02")
HIGH_THRESHOLD = Decimal("0.03")

GRID_LOW = Decimal("0.0005")
GRID_NORMAL = Decimal("0.0010")
GRID_HIGH = Decimal("0.0020")
GRID_EXTREME = Decimal("0.0030")


# ============================================================
# EXECUTION
# ============================================================

FEE_RATE = Decimal("0.001")

SLIPPAGE_RATE = Decimal("0.0002")


# ============================================================
# HELPERS
# ============================================================

def D(value):
    return Decimal(str(value))


# ============================================================
# INDICATORS
# ============================================================

def calculate_true_range(df):

    previous_close = df["close"].shift(1)

    tr1 = (
        df["high"] - df["low"]
    )

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

    df_1h = (
        df_1h
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    df_1d = (
        df_1d
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    return df_1h, df_1d


# ============================================================
# PREPARE DATA
# ============================================================

def prepare_data():

    df_1h, df_1d = load_market_data()

    df_1d["atr30"] = calculate_atr(
        df_1d,
        ATR_PERIOD,
    )

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
# VOLATILITY REGIME
# ============================================================

def determine_regime(
    atr,
    price,
):

    atr_percent = atr / price

    if atr_percent < LOW_THRESHOLD:

        return (
            "LOW",
            GRID_LOW,
            atr_percent,
        )

    if atr_percent < NORMAL_THRESHOLD:

        return (
            "NORMAL",
            GRID_NORMAL,
            atr_percent,
        )

    if atr_percent < HIGH_THRESHOLD:

        return (
            "HIGH",
            GRID_HIGH,
            atr_percent,
        )

    return (
        "EXTREME",
        GRID_EXTREME,
        atr_percent,
    )


# ============================================================
# GRID
# ============================================================

def build_grid(
    center,
    grid_percent,
):

    buys = []
    sells = []

    for level in range(
        1,
        BUY_LEVELS + 1,
    ):

        price = (
            center
            * (
                D("1")
                - grid_percent * level
            )
        )

        buys.append({
            "level": -level,
            "price": price,
            "size": ORDER_SIZE_USDT,
        })

    for level in range(
        1,
        SELL_LEVELS + 1,
    ):

        price = (
            center
            * (
                D("1")
                + grid_percent * level
            )
        )

        sells.append({
            "level": level,
            "price": price,
        })

    return buys, sells


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

        self.max_exposure = Decimal("0")

        self.trade_log = []

    # --------------------------------------------------------
    # EQUITY
    # --------------------------------------------------------

    def equity(self, price):

        return (
            self.cash
            + self.btc * price
        )

    # --------------------------------------------------------
    # EXPOSURE
    # --------------------------------------------------------

    def exposure_usdt(self, price):

        return self.btc * price

    # --------------------------------------------------------
    # EXPOSURE %
    # --------------------------------------------------------

    def exposure_percent(self, price):

        equity = self.equity(price)

        if equity <= 0:

            return Decimal("0")

        return (
            self.exposure_usdt(price)
            / equity
        )

    # --------------------------------------------------------
    # RISK
    # --------------------------------------------------------

    def can_buy(
        self,
        price,
        usdt_amount,
    ):

        if self.cash <= 0:

            return False

        current_exposure = (
            self.exposure_usdt(price)
        )

        if (
            current_exposure
            + usdt_amount
            > MAX_EXPOSURE_USDT
        ):

            return False

        total_cost = (
            usdt_amount
            * (
                D("1")
                + FEE_RATE
            )
        )

        return (
            total_cost
            <= self.cash
        )

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

        if not self.can_buy(
            price,
            usdt_amount,
        ):

            return False

        execution_price = (
            price
            * (
                D("1")
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

        if self.btc <= 0:

            return False

        btc_amount = min(
            btc_amount,
            self.btc,
        )

        execution_price = (
            price
            * (
                D("1")
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

    # --------------------------------------------------------
    # DRAW DOWN
    # --------------------------------------------------------

    def update_risk(
        self,
        price,
    ):

        equity = self.equity(price)

        exposure = (
            self.exposure_usdt(price)
        )

        if exposure > self.max_exposure:

            self.max_exposure = exposure

        if equity > self.equity_peak:

            self.equity_peak = equity

        if self.equity_peak > 0:

            drawdown = (
                self.equity_peak
                - equity
            ) / self.equity_peak

            if drawdown > self.max_drawdown:

                self.max_drawdown = drawdown


# ============================================================
# PAPER TRADING
# ============================================================

def run_paper_trading(df):

    portfolio = Portfolio()

    active_buys = {}

    active_sells = {}

    grid_center = None

    grid_percent = None

    previous_regime = None

    grid_rebuilds = 0

    regime_changes = 0

    start_time = None

    for _, row in df.iterrows():

        timestamp = row["timestamp"]

        close = D(row["close"])

        high = D(row["high"])

        low = D(row["low"])

        atr = row["atr30"]

        if pd.isna(atr):

            continue

        atr = D(atr)

        if atr <= 0:

            continue

        if start_time is None:

            start_time = timestamp

        regime, new_grid_percent, _ = (
            determine_regime(
                atr,
                close,
            )
        )

        # ----------------------------------------------------
        # INITIAL GRID / REGIME CHANGE
        # ----------------------------------------------------

        if (
            grid_center is None
            or regime != previous_regime
        ):

            if (
                previous_regime is not None
                and regime != previous_regime
            ):

                regime_changes += 1

            grid_center = close

            grid_percent = (
                new_grid_percent
            )

            (
                buy_levels,
                sell_levels,
            ) = build_grid(
                grid_center,
                grid_percent,
            )

            active_buys.clear()

            active_sells.clear()

            for order in buy_levels:

                active_buys[
                    order["level"]
                ] = order

            for order in sell_levels:

                active_sells[
                    order["level"]
                ] = order

            grid_rebuilds += 1

        previous_regime = regime

        # ----------------------------------------------------
        # BUY FILLS
        # ----------------------------------------------------

        filled_buys = []

        for level, order in list(
            active_buys.items()
        ):

            if low <= order["price"]:

                success = portfolio.buy(
                    price=order["price"],
                    usdt_amount=order["size"],
                    timestamp=timestamp,
                    level=level,
                )

                if success:

                    filled_buys.append(
                        level
                    )

        for level in filled_buys:

            order = active_buys.pop(
                level
            )

            # --------------------------------------------
            # BUY → SELL REPLACEMENT
            # --------------------------------------------

            sell_price = (
                order["price"]
                * (
                    D("1")
                    + grid_percent
                )
            )

            active_sells[level] = {
                "level": level,
                "price": sell_price,
            }

        # ----------------------------------------------------
        # SELL FILLS
        # ----------------------------------------------------

        filled_sells = []

        for level, order in list(
            active_sells.items()
        ):

            if high >= order["price"]:

                if portfolio.btc <= 0:

                    continue

                target_usdt = min(
                    ORDER_SIZE_USDT,
                    portfolio.exposure_usdt(
                        close
                    ),
                )

                btc_to_sell = (
                    target_usdt
                    / order["price"]
                )

                success = portfolio.sell(
                    price=order["price"],
                    btc_amount=btc_to_sell,
                    timestamp=timestamp,
                    level=level,
                )

                if success:

                    filled_sells.append(
                        level
                    )

        for level in filled_sells:

            order = active_sells.pop(
                level
            )

            # --------------------------------------------
            # SELL → BUY REPLACEMENT
            # --------------------------------------------

            buy_price = (
                order["price"]
                * (
                    D("1")
                    - grid_percent
                )
            )

            active_buys[level] = {
                "level": level,
                "price": buy_price,
                "size": ORDER_SIZE_USDT,
            }

        # ----------------------------------------------------
        # RISK
        # ----------------------------------------------------

        portfolio.update_risk(
            close
        )

    # ========================================================
    # RESULTS
    # ========================================================

    if start_time is None:

        raise RuntimeError(
            "No valid data available"
        )

    final_price = D(
        df.iloc[-1]["close"]
    )

    final_equity = (
        portfolio.equity(
            final_price
        )
    )

    profit = (
        final_equity
        - INITIAL_CAPITAL
    )

    return_percent = (
        profit
        / INITIAL_CAPITAL
        * D("100")
    )

    return {
        "start_time": start_time,
        "end_time": df.iloc[-1]["timestamp"],
        "initial_capital": INITIAL_CAPITAL,
        "final_equity": final_equity,
        "profit": profit,
        "return_percent": return_percent,
        "cash": portfolio.cash,
        "btc": portfolio.btc,
        "fees": portfolio.total_fees,
        "buys": portfolio.total_buys,
        "sells": portfolio.total_sells,
        "max_exposure": portfolio.max_exposure,
        "max_drawdown": portfolio.max_drawdown,
        "regime_changes": regime_changes,
        "grid_rebuilds": grid_rebuilds,
        "trades": portfolio.trade_log,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 75)
    print("          ADAPTIVE GRID BOT v4.0")
    print("             PAPER TRADING")
    print("=" * 75)

    print()
    print("Loading historical market data...")

    df = prepare_data()

    print(
        f"1H candles        : "
        f"{len(df):,}"
    )

    print(
        f"Period            : "
        f"{df['timestamp'].iloc[0]}"
        f" → "
        f"{df['timestamp'].iloc[-1]}"
    )

    print()
    print("=" * 75)
    print("PAPER CONFIGURATION")
    print("=" * 75)

    print(
        f"Initial Capital   : "
        f"{INITIAL_CAPITAL:.2f} USDT"
    )

    print(
        f"Max Exposure      : "
        f"{MAX_EXPOSURE_USDT:.2f} USDT"
    )

    print(
        f"Order Size        : "
        f"{ORDER_SIZE_USDT:.2f} USDT"
    )

    print(
        f"Grid Levels       : "
        f"{BUY_LEVELS} BUY / "
        f"{SELL_LEVELS} SELL"
    )

    print(
        f"Fee               : "
        f"{FEE_RATE * 100:.3f}%"
    )

    print(
        f"Slippage          : "
        f"{SLIPPAGE_RATE * 100:.3f}%"
    )

    print()
    print("Running v4 paper simulation...")

    result = run_paper_trading(
        df
    )

    print()
    print("=" * 75)
    print("                         RESULTS")
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

    print(
        f"Max Exposure      : "
        f"{result['max_exposure']:.2f} USDT"
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
        f"Regime changes    : "
        f"{result['regime_changes']}"
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
    print("              NO REAL ORDERS SENT")
    print("=" * 75)
    print()


if __name__ == "__main__":

    main()