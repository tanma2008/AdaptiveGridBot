import pandas as pd
from decimal import Decimal


# ============================================================
# CONFIG
# ============================================================

DATA_FILE_1H = "btc_usdt_1h.csv"
DATA_FILE_1D = "btc_usdt_1d.csv"

INITIAL_CAPITAL = Decimal("100")

MAX_EXPOSURE = Decimal("0.30")
ATR_MULTIPLIER = Decimal("0.30")

FEE_RATE = Decimal("0.001")
SLIPPAGE_RATE = Decimal("0.0002")

GRID_BUY_LEVELS = 5
GRID_SELL_LEVELS = 3


# ============================================================
# LOAD DATA
# ============================================================

def load_data():

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
# INDICATORS
# ============================================================

def add_indicators(df_1h, df_1d):

    df_1h["ema50"] = (
        df_1h["close"]
        .ewm(span=50, adjust=False)
        .mean()
    )

    df_1h["ema200"] = (
        df_1h["close"]
        .ewm(span=200, adjust=False)
        .mean()
    )

    previous_close = df_1d["close"].shift(1)

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
# TREND
# ============================================================

def get_trend(row):

    price = row["close"]
    ema50 = row["ema50"]
    ema200 = row["ema200"]

    if price > ema50 and ema50 > ema200:
        return "UP"

    if price < ema50 and ema50 < ema200:
        return "DOWN"

    return "SIDEWAY"


# ============================================================
# REPORT ENGINE
# ============================================================

def run_report(df):

    cash = INITIAL_CAPITAL
    btc = Decimal("0")

    peak_equity = INITIAL_CAPITAL
    max_drawdown = Decimal("0")

    total_fees = Decimal("0")

    buys = 0
    sells = 0

    trend_changes = 0

    previous_trend = None

    equity_curve = []

    trade_pnl = []

    avg_entry = Decimal("0")
    entry_btc = Decimal("0")

    # Grid state
    grid_center = None
    grid_distance = None

    buy_orders = []
    sell_orders = []

    for _, row in df.iterrows():

        if pd.isna(row["atr30"]):
            continue

        timestamp = row["timestamp"]

        open_price = Decimal(str(row["open"]))
        high = Decimal(str(row["high"]))
        low = Decimal(str(row["low"]))
        close = Decimal(str(row["close"]))

        atr30 = Decimal(str(row["atr30"]))

        trend = get_trend(row)

        # ----------------------------------------------------
        # Trend change
        # ----------------------------------------------------

        if previous_trend is None or trend != previous_trend:

            trend_changes += 1

            grid_center = close

            grid_distance = (
                atr30
                * ATR_MULTIPLIER
            )

            buy_orders = []

            sell_orders = []

            for level in range(
                1,
                GRID_BUY_LEVELS + 1,
            ):

                buy_orders.append({
                    "price":
                        grid_center
                        - grid_distance * level
                })

            for level in range(
                1,
                GRID_SELL_LEVELS + 1,
            ):

                sell_orders.append({
                    "price":
                        grid_center
                        + grid_distance * level
                })

        previous_trend = trend

        # ----------------------------------------------------
        # Equity before fills
        # ----------------------------------------------------

        equity_before = (
            cash
            + btc * close
        )

        # ----------------------------------------------------
        # BUY fills
        # ----------------------------------------------------

        remaining_buys = []

        for order in buy_orders:

            order_price = order["price"]

            if low <= order_price:

                max_exposure_value = (
                    (
                        cash
                        + btc * close
                    )
                    * MAX_EXPOSURE
                )

                current_btc_value = (
                    btc * close
                )

                available_exposure = (
                    max_exposure_value
                    - current_btc_value
                )

                if available_exposure > 0:

                    # Equal allocation across
                    # remaining buy levels.
                    usdt_size = (
                        available_exposure
                        / Decimal(
                            str(
                                GRID_BUY_LEVELS
                            )
                        )
                    )

                    if usdt_size >= Decimal("1"):

                        execution_price = (
                            order_price
                            * (
                                Decimal("1")
                                + SLIPPAGE_RATE
                            )
                        )

                        fee = (
                            usdt_size
                            * FEE_RATE
                        )

                        total_cost = (
                            usdt_size
                            + fee
                        )

                        if total_cost <= cash:

                            bought_btc = (
                                usdt_size
                                / execution_price
                            )

                            # Average entry
                            old_cost = (
                                avg_entry
                                * entry_btc
                            )

                            new_cost = (
                                old_cost
                                + usdt_size
                            )

                            entry_btc += bought_btc

                            btc += bought_btc

                            cash -= total_cost

                            avg_entry = (
                                new_cost
                                / entry_btc
                            )

                            total_fees += fee

                            buys += 1

                            continue

            remaining_buys.append(order)

        buy_orders = remaining_buys

        # ----------------------------------------------------
        # SELL fills
        # ----------------------------------------------------

        remaining_sells = []

        for order in sell_orders:

            order_price = order["price"]

            if high >= order_price:

                if btc > 0:

                    execution_price = (
                        order_price
                        * (
                            Decimal("1")
                            - SLIPPAGE_RATE
                        )
                    )

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

                    sell_btc = (
                        target_value
                        / execution_price
                    )

                    sell_btc = min(
                        sell_btc,
                        btc,
                    )

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

                    # Realized P&L
                    cost_basis = (
                        avg_entry
                        * sell_btc
                    )

                    pnl = (
                        net
                        - cost_basis
                    )

                    trade_pnl.append(
                        pnl
                    )

                    btc -= sell_btc

                    cash += net

                    total_fees += fee

                    sells += 1

                    entry_btc -= sell_btc

                    if entry_btc > 0:

                        # Keep avg entry
                        # approximately unchanged.
                        pass

                    else:

                        entry_btc = Decimal("0")
                        avg_entry = Decimal("0")

                    continue

            remaining_sells.append(order)

        sell_orders = remaining_sells

        # ----------------------------------------------------
        # Equity
        # ----------------------------------------------------

        equity = (
            cash
            + btc * close
        )

        if equity > peak_equity:

            peak_equity = equity

        if peak_equity > 0:

            drawdown = (
                peak_equity - equity
            ) / peak_equity

            if drawdown > max_drawdown:

                max_drawdown = drawdown

        equity_curve.append({
            "timestamp": timestamp,
            "equity": float(equity),
            "btc_price": float(close),
            "cash": float(cash),
            "btc": float(btc),
            "trend": trend,
        })

    curve = pd.DataFrame(
        equity_curve
    )

    final_equity = Decimal(
        str(curve.iloc[-1]["equity"])
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

    winning_trades = sum(
        1
        for pnl in trade_pnl
        if pnl > 0
    )

    losing_trades = sum(
        1
        for pnl in trade_pnl
        if pnl < 0
    )

    total_wins = sum(
        pnl
        for pnl in trade_pnl
        if pnl > 0
    )

    total_losses = abs(
        sum(
            pnl
            for pnl in trade_pnl
            if pnl < 0
        )
    )

    if total_losses > 0:

        profit_factor = (
            total_wins
            / total_losses
        )

    else:

        profit_factor = Decimal("0")

    if winning_trades + losing_trades > 0:

        win_rate = (
            Decimal(
                str(winning_trades)
            )
            / Decimal(
                str(
                    winning_trades
                    + losing_trades
                )
            )
            * Decimal("100")
        )

    else:

        win_rate = Decimal("0")

    return {
        "curve": curve,
        "final_equity": final_equity,
        "profit": profit,
        "return_pct": return_pct,
        "max_drawdown": max_drawdown,
        "fees": total_fees,
        "buys": buys,
        "sells": sells,
        "trend_changes": trend_changes,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 75)
    print("          ADAPTIVE GRID BOT - BACKTEST REPORT")
    print("=" * 75)

    df_1h, df_1d = load_data()

    df = add_indicators(
        df_1h,
        df_1d,
    )

    print()
    print(
        f"Data              : "
        f"{len(df):,} × 1H candles"
    )

    print(
        f"Period            : "
        f"{df['timestamp'].iloc[0]}"
        f" → "
        f"{df['timestamp'].iloc[-1]}"
    )

    print()
    print("Running report...")

    result = run_report(df)

    print()
    print("=" * 75)
    print("                         RESULTS")
    print("=" * 75)

    print()

    print(
        f"Initial Capital    : "
        f"{INITIAL_CAPITAL:.2f} USDT"
    )

    print(
        f"Final Equity       : "
        f"{result['final_equity']:.2f} USDT"
    )

    print(
        f"Profit / Loss      : "
        f"{result['profit']:.2f} USDT"
    )

    print(
        f"Return             : "
        f"{result['return_pct']:.2f}%"
    )

    print()

    print(
        f"Max Drawdown       : "
        f"{result['max_drawdown'] * 100:.2f}%"
    )

    print(
        f"Fees               : "
        f"{result['fees']:.4f} USDT"
    )

    print()

    print(
        f"BUY fills          : "
        f"{result['buys']}"
    )

    print(
        f"SELL fills         : "
        f"{result['sells']}"
    )

    print(
        f"Trend changes      : "
        f"{result['trend_changes']}"
    )

    print()

    print(
        f"Winning trades     : "
        f"{result['winning_trades']}"
    )

    print(
        f"Losing trades      : "
        f"{result['losing_trades']}"
    )

    print(
        f"Win rate           : "
        f"{result['win_rate']:.2f}%"
    )

    print(
        f"Profit factor      : "
        f"{result['profit_factor']:.2f}"
    )

    # --------------------------------------------------------
    # Save equity curve
    # --------------------------------------------------------

    result["curve"].to_csv(
        "backtest_equity.csv",
        index=False,
    )

    print()
    print(
        "Saved: backtest_equity.csv"
    )

    print()
    print("=" * 75)
    print("                    REPORT COMPLETE")
    print("=" * 75)
    print()


if __name__ == "__main__":
    main()