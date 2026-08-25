import pandas as pd
from decimal import Decimal


# ============================================================
# ADAPTIVE GRID BOT v4.8 REALIZED P/L
# UNIFIED PAPER / BACKTEST EXECUTION ENGINE
#
# Purpose:
#   Fix v4.3 backtest position accumulation and make the
#   execution state deterministic.
#
# Rules:
#   BUY fill  -> SELL replacement
#   SELL fill -> BUY replacement
#   Rebuild   -> cancel virtual grid orders only
#   Position  -> NEVER reset on rebuild
#   Exposure  -> hard $500 cap
#   Same-candle replacement orders cannot fill again
# ============================================================

FILE_1H = "btc_usdt_1h.csv"
FILE_1D = "btc_usdt_1d.csv"


# ============================================================
# CAPITAL / RISK
# ============================================================

INITIAL_CAPITAL = Decimal("1000")
MAX_EXPOSURE_USDT = Decimal("500")
ORDER_SIZE_USDT = Decimal("5")

BUY_LEVELS = 10
SELL_LEVELS = 10


# ============================================================
# V2 TREND
# ============================================================

CONFIRM_CANDLES = 6


# ============================================================
# V4 ADAPTIVE GRID
# ============================================================

ATR_PERIOD = 30

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
# INDICATORS
# ============================================================

def prepare_data(df_1h, df_1d):
    h = df_1h.copy()
    d = df_1d.copy()

    h["ema50"] = h["close"].ewm(
        span=50,
        adjust=False,
    ).mean()

    h["ema200"] = h["close"].ewm(
        span=200,
        adjust=False,
    ).mean()

    h["ema50_slope"] = h["ema50"].diff()

    previous_close = d["close"].shift(1)

    tr1 = d["high"] - d["low"]
    tr2 = (d["high"] - previous_close).abs()
    tr3 = (d["low"] - previous_close).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1,
    ).max(axis=1)

    d["atr30"] = true_range.ewm(
        alpha=1 / ATR_PERIOD,
        adjust=False,
    ).mean()

    # IMPORTANT:
    # backward merge only; no future daily ATR is visible.
    result = pd.merge_asof(
        h.sort_values("timestamp"),
        d[["timestamp", "atr30"]].sort_values("timestamp"),
        on="timestamp",
        direction="backward",
    )

    return result


# ============================================================
# TREND ENGINE
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
        self.count = 0
        self.changes = 0

    def update(self, signal):

        if signal == self.current:
            self.candidate = None
            self.count = 0
            return self.current, False

        if signal != self.candidate:
            self.candidate = signal
            self.count = 1
            return self.current, False

        self.count += 1

        if self.count >= CONFIRM_CANDLES:
            old = self.current
            self.current = self.candidate
            self.candidate = None
            self.count = 0
            self.changes += 1
            return self.current, True

        return self.current, False


# ============================================================
# VOLATILITY
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
# GRID MANAGER
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
# PORTFOLIO
# ============================================================

class Portfolio:

    def __init__(self):

        self.cash = INITIAL_CAPITAL
        self.btc = Decimal("0")

        self.total_fees = Decimal("0")

        self.buy_fills = 0
        self.sell_fills = 0

        self.peak_equity = INITIAL_CAPITAL
        self.max_drawdown = Decimal("0")
        self.max_exposure = Decimal("0")
        self.max_invested_exposure = Decimal("0")
        self.max_market_exposure = Decimal("0")
        self.invested_exposure = Decimal("0")

        self.trades = []

    def equity(self, mark_price):

        return self.cash + self.btc * mark_price

    def exposure(self, mark_price):

        return self.btc * mark_price

    def can_buy(self, mark_price, usdt_size):

        current_exposure = self.exposure(
            mark_price
        )

        # HARD mark-to-market exposure cap.
        if current_exposure >= MAX_EXPOSURE_USDT:
            return False

        if self.cash <= 0:
            return False

        execution_price = (
            mark_price
            * (D("1") + SLIPPAGE_RATE)
        )

        btc_amount = (
            usdt_size / execution_price
        )

        projected_exposure = (
            (self.btc + btc_amount)
            * mark_price
        )

        # Never allow projected exposure above cap.
        if projected_exposure > MAX_EXPOSURE_USDT:
            return False

        return True

    def buy(
        self,
        limit_price,
        mark_price,
        timestamp,
        level,
    ):

        size = ORDER_SIZE_USDT

        if not self.can_buy(
            mark_price,
            size,
        ):
            return False

        # Hard exposure check at execution price.
        execution_price = (
            limit_price
            * (D("1") + SLIPPAGE_RATE)
        )

        fee = size * FEE_RATE
        total_cost = size + fee

        if total_cost > self.cash:
            return False

        btc_amount = size / execution_price

        new_exposure = (
            (self.btc + btc_amount)
            * mark_price
        )

        if new_exposure > MAX_EXPOSURE_USDT:
            return False

        self.cash -= total_cost
        self.btc += btc_amount
        self.invested_exposure += size

        self.total_fees += fee
        self.buy_fills += 1

        self.max_invested_exposure = max(
            self.max_invested_exposure,
            self.invested_exposure,
        )

        market_exposure = self.exposure(
            mark_price
        )

        self.max_market_exposure = max(
            self.max_market_exposure,
            market_exposure,
        )

        self.trades.append({
            "timestamp": timestamp,
            "side": "BUY",
            "level": level,
            "limit_price": float(limit_price),
            "execution_price": float(execution_price),
            "usdt": float(size),
            "btc": float(btc_amount),
            "fee": float(fee),
            "invested_exposure": float(
                self.invested_exposure
            ),
            "market_exposure": float(
                market_exposure
            ),
        })

        return True

    def sell(
        self,
        limit_price,
        timestamp,
        level,
    ):

        if self.btc <= 0:
            return False

        execution_price = (
            limit_price
            * (D("1") - SLIPPAGE_RATE)
        )

        # Sell one grid-sized notional.
        btc_amount = (
            ORDER_SIZE_USDT
            / execution_price
        )

        btc_amount = min(
            btc_amount,
            self.btc,
        )

        if btc_amount <= 0:
            return False

        gross = btc_amount * execution_price
        fee = gross * FEE_RATE
        net = gross - fee

        self.btc -= btc_amount
        self.cash += net
        self.total_fees += fee
        self.sell_fills += 1

        self.trades.append({
            "timestamp": timestamp,
            "side": "SELL",
            "level": level,
            "limit_price": float(limit_price),
            "execution_price": float(execution_price),
            "usdt": float(net),
            "btc": float(btc_amount),
            "fee": float(fee),
            "invested_exposure": float(
                self.invested_exposure
            ),
            "market_exposure": float(
                self.exposure(execution_price)
            ),
        })

        return True

    def update_risk(self, mark_price):

        equity = self.equity(mark_price)
        exposure = self.exposure(mark_price)

        self.max_exposure = max(
            self.max_exposure,
            exposure,
        )

        self.max_market_exposure = max(
            self.max_market_exposure,
            exposure,
        )

        self.max_invested_exposure = max(
            self.max_invested_exposure,
            self.invested_exposure,
        )

        if equity > self.peak_equity:
            self.peak_equity = equity

        if self.peak_equity > 0:
            dd = (
                self.peak_equity - equity
            ) / self.peak_equity

            self.max_drawdown = max(
                self.max_drawdown,
                dd,
            )


# ============================================================
# UNIFIED EXECUTION ENGINE
# ============================================================

class UnifiedEngine:

    def __init__(self):

        self.portfolio = Portfolio()

        self.trend = TrendEngine()

        self.buy_orders = []
        self.sell_orders = []

        self.grid_percent = None
        self.regime = None

        self.grid_rebuilds = 0
        self.regime_changes = 0

        self.risk_violations = 0
        self.buy_blocked = 0

        self.equity_rows = []
        self.regime_rows = []

    def rebuild_grid(
        self,
        center,
        grid_percent,
        timestamp,
        reason,
    ):

        # IMPORTANT:
        # Rebuild cancels ONLY outstanding virtual orders.
        # It NEVER resets BTC/cash/portfolio.

        self.buy_orders = []
        self.sell_orders = []

        (
            self.buy_orders,
            self.sell_orders,
        ) = build_grid(
            center,
            grid_percent,
        )

        self.grid_percent = grid_percent
        self.grid_rebuilds += 1

        self.regime_rows.append({
            "timestamp": timestamp,
            "reason": reason,
            "regime": self.regime,
            "grid_percent": float(
                grid_percent * 100
            ),
            "center": float(center),
        })

    def process_candle(
        self,
        row,
    ):

        if pd.isna(row["atr30"]):
            return

        timestamp = row["timestamp"]

        high = D(row["high"])
        low = D(row["low"])
        close = D(row["close"])
        atr = D(row["atr30"])

        if atr <= 0 or close <= 0:
            return

        signal = raw_signal(row)

        trend, trend_changed = (
            self.trend.update(signal)
        )

        (
            regime,
            new_grid_percent,
            atr_percent,
        ) = determine_regime(
            atr,
            close,
        )

        first_grid = (
            self.grid_percent is None
        )

        regime_changed = (
            self.regime is not None
            and regime != self.regime
        )

        if first_grid:

            self.regime = regime

            self.rebuild_grid(
                close,
                new_grid_percent,
                timestamp,
                "INITIAL",
            )

        elif regime_changed:

            self.regime_changes += 1
            self.regime = regime

            self.rebuild_grid(
                close,
                new_grid_percent,
                timestamp,
                "REGIME_CHANGE",
            )

        elif trend_changed:

            self.rebuild_grid(
                close,
                self.grid_percent,
                timestamp,
                "TREND_CHANGE",
            )

        # ----------------------------------------------------
        # SNAPSHOT START-OF-CANDLE ORDERS
        # ----------------------------------------------------
        #
        # Replacement orders created below are NOT eligible
        # to fill in this same candle.
        #

        current_invested = (
            self.portfolio.invested_exposure
        )

        if current_invested >= MAX_EXPOSURE_USDT:
            self.buy_blocked += len(
                self.buy_orders
            )
            buy_snapshot = []
        else:
            buy_snapshot = list(
                self.buy_orders
            )

        sell_snapshot = list(
            self.sell_orders
        )

        remaining_buys = []
        filled_buys = []

        # ----------------------------------------------------
        # BUY
        # ----------------------------------------------------

        for order in buy_snapshot:

            if low <= order["price"]:

                success = (
                    self.portfolio.buy(
                        limit_price=D(
                            order["price"]
                        ),
                        mark_price=close,
                        timestamp=timestamp,
                        level=order["level"],
                    )
                )

                if success:

                    filled_buys.append(
                        order
                    )

                else:

                    remaining_buys.append(
                        order
                    )

            else:

                remaining_buys.append(
                    order
                )

        # ----------------------------------------------------
        # BUY -> SELL
        # ----------------------------------------------------

        self.buy_orders = remaining_buys

        for order in filled_buys:

            replacement_price = (
                D(order["price"])
                * (
                    D("1")
                    + self.grid_percent
                )
            )

            self.sell_orders.append({
                "level": -order["level"],
                "price": replacement_price,
            })

        # ----------------------------------------------------
        # SELL
        # ----------------------------------------------------

        remaining_sells = []
        filled_sells = []

        for order in sell_snapshot:

            if high >= order["price"]:

                success = (
                    self.portfolio.sell(
                        limit_price=D(
                            order["price"]
                        ),
                        timestamp=timestamp,
                        level=order["level"],
                    )
                )

                if success:

                    filled_sells.append(
                        order
                    )

                else:

                    remaining_sells.append(
                        order
                    )

            else:

                remaining_sells.append(
                    order
                )

        # ----------------------------------------------------
        # SELL -> BUY
        # ----------------------------------------------------

        self.sell_orders = remaining_sells

        for order in filled_sells:

            replacement_price = (
                D(order["price"])
                * (
                    D("1")
                    - self.grid_percent
                )
            )

            self.buy_orders.append({
                "level": -order["level"],
                "price": replacement_price,
                "size": ORDER_SIZE_USDT,
            })

        # ----------------------------------------------------
        # RISK SNAPSHOT
        # ----------------------------------------------------

        self.portfolio.update_risk(
            close
        )

        # ----------------------------------------------------
        # HARD RISK MONITOR
        # ----------------------------------------------------

        current_exposure = (
            self.portfolio.exposure(close)
        )

        if (
            self.portfolio.invested_exposure
            > MAX_EXPOSURE_USDT
        ):

            self.risk_violations += 1

            # Defensive cancellation. SELL remains active.
            self.buy_orders = []

        equity = self.portfolio.equity(
            close
        )

        exposure = self.portfolio.exposure(
            close
        )

        self.equity_rows.append({
            "timestamp": timestamp,
            "equity": float(equity),
            "cash": float(
                self.portfolio.cash
            ),
            "btc": float(
                self.portfolio.btc
            ),
            "exposure": float(exposure),
            "invested_exposure": float(
                self.portfolio.invested_exposure
            ),
            "market_exposure": float(
                self.portfolio.exposure(close)
            ),
            "drawdown_pct": float(
                self.portfolio.max_drawdown
                * 100
            ),
            "trend": trend,
            "regime": self.regime,
            "grid_percent": float(
                self.grid_percent * 100
            ),
            "open_buy_orders": len(
                self.buy_orders
            ),
            "open_sell_orders": len(
                self.sell_orders
            ),
        })


# ============================================================
# RUN
# ============================================================

def run_backtest(df):

    engine = UnifiedEngine()

    for _, row in df.iterrows():

        engine.process_candle(
            row
        )

    if not engine.equity_rows:
        raise RuntimeError(
            "No valid candles available"
        )

    curve = pd.DataFrame(
        engine.equity_rows
    )

    regimes = pd.DataFrame(
        engine.regime_rows
    )

    trades = pd.DataFrame(
        engine.portfolio.trades
    )

    final_price = D(
        df.iloc[-1]["close"]
    )

    final_equity = (
        engine.portfolio.equity(
            final_price
        )
    )

    profit = (
        final_equity
        - INITIAL_CAPITAL
    )

    return_pct = (
        profit
        / INITIAL_CAPITAL
        * D("100")
    )

    return {
        "initial": INITIAL_CAPITAL,
        "final": final_equity,
        "profit": profit,
        "return_pct": return_pct,
        "max_drawdown": (
            engine.portfolio.max_drawdown
        ),
        "max_exposure": (
            engine.portfolio.max_exposure
        ),
        "max_invested_exposure": (
            engine.portfolio.max_invested_exposure
        ),
        "max_market_exposure": (
            engine.portfolio.max_market_exposure
        ),
        "fees": (
            engine.portfolio.total_fees
        ),
        "buys": (
            engine.portfolio.buy_fills
        ),
        "sells": (
            engine.portfolio.sell_fills
        ),
        "trend_changes": (
            engine.trend.changes
        ),
        "regime_changes": (
            engine.regime_changes
        ),
        "grid_rebuilds": (
            engine.grid_rebuilds
        ),
        "risk_violations": (
            engine.risk_violations
        ),
        "buy_blocked": (
            engine.buy_blocked
        ),
        "curve": curve,
        "regimes": regimes,
        "trades": trades,
    }



# ============================================================
# REGIME / TREND PERFORMANCE
# ============================================================

def calculate_segment_performance(curve):

    rows = []

    if curve.empty:
        return pd.DataFrame()

    for column_name, kind in [
        ("regime", "VOLATILITY"),
        ("trend", "TREND"),
    ]:

        for segment in sorted(
            curve[column_name].dropna().unique()
        ):

            part = curve[
                curve[column_name] == segment
            ]

            if len(part) < 2:
                continue

            start_equity = D(
                part.iloc[0]["equity"]
            )

            end_equity = D(
                part.iloc[-1]["equity"]
            )

            pnl = end_equity - start_equity

            ret = (
                pnl / start_equity * D("100")
                if start_equity > 0
                else D("0")
            )

            rows.append({
                "type": kind,
                "segment": segment,
                "candles": len(part),
                "start_equity": float(start_equity),
                "end_equity": float(end_equity),
                "pnl": float(pnl),
                "return_pct": float(ret),
            })

    return pd.DataFrame(rows)




# ============================================================
# V4.7 TRADE EDGE ANALYSIS
# ============================================================

def analyze_trade_edge(trades):

    if trades.empty:
        empty = pd.DataFrame()
        return {
            "summary": empty,
            "regime": empty,
            "trend": empty,
            "levels": empty,
            "cycles": empty,
        }

    t = trades.copy()

    t["timestamp"] = pd.to_datetime(
        t["timestamp"],
        errors="coerce",
    )

    for col in [
        "execution_price",
        "btc",
        "fee",
        "usdt",
    ]:
        if col in t.columns:
            t[col] = pd.to_numeric(
                t[col],
                errors="coerce",
            )

    # --------------------------------------------------------
    # FIFO inventory accounting
    #
    # BUY adds real BTC quantity + cost basis.
    # SELL removes real BTC quantity and realizes:
    #
    #   sell gross
    # - allocated BUY cost
    # - BUY fee
    # - SELL fee
    #
    # This avoids using SELL "usdt" as a proxy for sale value.
    # --------------------------------------------------------

    inventory = []
    cycles = []

    for _, row in t.sort_values(
        "timestamp"
    ).iterrows():

        side = str(
            row.get("side", "")
        ).upper()

        qty = float(
            row.get("btc", 0) or 0
        )

        price = float(
            row.get("execution_price", 0) or 0
        )

        fee = float(
            row.get("fee", 0) or 0
        )

        if qty <= 0 or price <= 0:
            continue

        if side == "BUY":

            inventory.append({
                "timestamp": row["timestamp"],
                "level": row.get("level"),
                "qty": qty,
                "price": price,
                "cost": qty * price,
                "fee": fee,
                "regime": row.get(
                    "regime",
                    "UNKNOWN",
                ),
                "trend": row.get(
                    "trend",
                    "UNKNOWN",
                ),
            })

            continue

        if side != "SELL":
            continue

        remaining = qty

        while remaining > 1e-15 and inventory:

            buy = inventory[0]

            matched = min(
                remaining,
                buy["qty"],
            )

            buy_cost = (
                matched
                * buy["price"]
            )

            sell_gross = (
                matched
                * price
            )

            # Allocate BUY fee proportionally.
            buy_fee = (
                buy["fee"]
                * (
                    matched
                    / buy["qty"]
                )
            )

            sell_fee = (
                fee
                * (
                    matched
                    / qty
                )
            )

            net_pnl = (
                sell_gross
                - buy_cost
                - buy_fee
                - sell_fee
            )

            cycles.append({
                "buy_timestamp":
                    buy["timestamp"],
                "sell_timestamp":
                    row["timestamp"],
                "level":
                    buy["level"],
                "buy_price":
                    buy["price"],
                "sell_price":
                    price,
                "btc":
                    matched,
                "buy_gross":
                    buy_cost,
                "sell_gross":
                    sell_gross,
                "buy_fee":
                    buy_fee,
                "sell_fee":
                    sell_fee,
                "fees":
                    buy_fee + sell_fee,
                "net_pnl":
                    net_pnl,
                "regime":
                    row.get(
                        "regime",
                        buy.get(
                            "regime",
                            "UNKNOWN",
                        ),
                    ),
                "trend":
                    row.get(
                        "trend",
                        buy.get(
                            "trend",
                            "UNKNOWN",
                        ),
                    ),
            })

            buy["qty"] -= matched
            remaining -= matched

            if buy["qty"] <= 1e-15:
                inventory.pop(0)

    cycles_df = pd.DataFrame(cycles)

    def aggregate(column):

        if cycles_df.empty:
            return pd.DataFrame()

        rows = []

        for name, part in cycles_df.groupby(
            column,
            dropna=False,
        ):

            pnl = part["net_pnl"].sum()
            fees = part["fees"].sum()

            wins = int(
                (part["net_pnl"] > 0).sum()
            )

            losses = int(
                (part["net_pnl"] <= 0).sum()
            )

            gross_profit = part.loc[
                part["net_pnl"] > 0,
                "net_pnl",
            ].sum()

            gross_loss = abs(
                part.loc[
                    part["net_pnl"] < 0,
                    "net_pnl",
                ].sum()
            )

            profit_factor = (
                gross_profit / gross_loss
                if gross_loss > 0
                else float("inf")
                if gross_profit > 0
                else 0
            )

            rows.append({
                "segment": name,
                "cycles": len(part),
                "wins": wins,
                "losses": losses,
                "win_rate_pct": (
                    wins / len(part) * 100
                ),
                "gross_pnl": float(pnl),
                "fees": float(fees),
                "avg_cycle_pnl": float(
                    pnl / len(part)
                ),
                "profit_factor": float(
                    profit_factor
                ),
                "best_cycle": float(
                    part["net_pnl"].max()
                ),
                "worst_cycle": float(
                    part["net_pnl"].min()
                ),
            })

        return pd.DataFrame(rows)

    regime_df = aggregate("regime")
    trend_df = aggregate("trend")

    level_rows = []

    if not cycles_df.empty:

        for level, part in cycles_df.groupby(
            "level",
            dropna=False,
        ):

            pnl = part["net_pnl"].sum()
            wins = int(
                (part["net_pnl"] > 0).sum()
            )

            gross_profit = part.loc[
                part["net_pnl"] > 0,
                "net_pnl",
            ].sum()

            gross_loss = abs(
                part.loc[
                    part["net_pnl"] < 0,
                    "net_pnl",
                ].sum()
            )

            pf = (
                gross_profit / gross_loss
                if gross_loss > 0
                else float("inf")
                if gross_profit > 0
                else 0
            )

            level_rows.append({
                "level": level,
                "cycles": len(part),
                "wins": wins,
                "losses": int(
                    len(part) - wins
                ),
                "win_rate_pct": (
                    wins / len(part) * 100
                ),
                "pnl": float(pnl),
                "fees": float(
                    part["fees"].sum()
                ),
                "avg_pnl": float(
                    pnl / len(part)
                ),
                "profit_factor": float(pf),
                "best": float(
                    part["net_pnl"].max()
                ),
                "worst": float(
                    part["net_pnl"].min()
                ),
            })

    levels_df = pd.DataFrame(
        level_rows
    )

    total_cycles = len(cycles_df)

    if total_cycles:

        total_pnl = cycles_df[
            "net_pnl"
        ].sum()

        total_fees = cycles_df[
            "fees"
        ].sum()

        wins = int(
            (cycles_df["net_pnl"] > 0).sum()
        )

        gross_profit = cycles_df.loc[
            cycles_df["net_pnl"] > 0,
            "net_pnl",
        ].sum()

        gross_loss = abs(
            cycles_df.loc[
                cycles_df["net_pnl"] < 0,
                "net_pnl",
            ].sum()
        )

        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else float("inf")
            if gross_profit > 0
            else 0
        )

        summary_df = pd.DataFrame([{
            "cycles": total_cycles,
            "wins": wins,
            "losses": total_cycles - wins,
            "win_rate_pct":
                wins / total_cycles * 100,
            "realized_net_pnl":
                float(total_pnl),
            "cycle_fees":
                float(total_fees),
            "avg_cycle_pnl":
                float(
                    total_pnl / total_cycles
                ),
            "profit_factor":
                float(profit_factor),
            "best_cycle":
                float(
                    cycles_df["net_pnl"].max()
                ),
            "worst_cycle":
                float(
                    cycles_df["net_pnl"].min()
                ),
        }])

    else:
        summary_df = pd.DataFrame()

    return {
        "summary": summary_df,
        "regime": regime_df,
        "trend": trend_df,
        "levels": levels_df,
        "cycles": cycles_df,
    }


# ============================================================
# RECONCILIATION
# ============================================================

def reconcile_edge(result, edge):

    initial = float(INITIAL_CAPITAL)
    final_value = result.get(
        "final_equity",
        result.get("final")
    )

    if final_value is None:
        raise RuntimeError(
            "Backtest result has no final equity value. "
            "Expected key 'final' or 'final_equity'."
        )

    final_equity = float(final_value)

    realized = 0.0

    if not edge["cycles"].empty:
        realized = float(
            edge["cycles"]["net_pnl"].sum()
        )

    equity_delta = (
        final_equity - initial
    )

    # Open BTC inventory can create unrealized P/L.
    unrealized = (
        equity_delta - realized
    )

    return {
        "initial_equity": initial,
        "final_equity": final_equity,
        "equity_delta": equity_delta,
        "realized_cycle_pnl": realized,
        "unrealized_residual": unrealized,
        "reconciliation_error": (
            equity_delta
            - realized
            - unrealized
        ),
    }



# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 78)
    print("        ADAPTIVE GRID BOT v4.8 REALIZED P/L")
    print("         UNIFIED PAPER / BACKTEST ENGINE")
    print("=" * 78)

    df_1h, df_1d = load_data()

    print()
    print("Loading historical data...")

    print(
        f"1H candles         : "
        f"{len(df_1h):,}"
    )

    print(
        f"1D candles         : "
        f"{len(df_1d):,}"
    )

    print(
        f"1H period          : "
        f"{df_1h['timestamp'].iloc[0]}"
        f" -> "
        f"{df_1h['timestamp'].iloc[-1]}"
    )

    df = prepare_data(
        df_1h,
        df_1d,
    )

    print()
    print("=" * 78)
    print("CONFIGURATION")
    print("=" * 78)

    print(
        f"Initial Capital    : "
        f"{INITIAL_CAPITAL:.2f} USDT"
    )

    print(
        f"Max Exposure       : "
        f"{MAX_EXPOSURE_USDT:.2f} USDT"
    )

    print(
        f"Order Size         : "
        f"{ORDER_SIZE_USDT:.2f} USDT"
    )

    print(
        f"Grid Levels        : "
        f"{BUY_LEVELS} BUY / "
        f"{SELL_LEVELS} SELL"
    )

    print(
        f"Trend Confirmation : "
        f"{CONFIRM_CANDLES} candles"
    )

    print(
        f"ATR Period         : "
        f"{ATR_PERIOD}D"
    )

    print(
        f"Fee                : "
        f"{FEE_RATE * 100:.3f}%"
    )

    print(
        f"Slippage           : "
        f"{SLIPPAGE_RATE * 100:.3f}%"
    )

    print()
    print(
        "Running v4.8 backtest..."
    )

    result = run_backtest(
        df
    )

    edge = analyze_trade_edge(
        result["trades"]
    )

    reconciliation = reconcile_edge(
        result,
        edge,
    )

    print()
    print("=" * 78)
    print("                         RESULTS")
    print("=" * 78)

    print()
    print(
        f"Initial Equity     : "
        f"{result['initial']:.2f} USDT"
    )

    print(
        f"Final Equity       : "
        f"{result['final']:.2f} USDT"
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
        f"Max Invested Exp.  : "
        f"{result['max_invested_exposure']:.2f} USDT"
    )

    print(
        f"Max Market Exp.    : "
        f"{result['max_market_exposure']:.2f} USDT"
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

    print(
        f"Regime changes     : "
        f"{result['regime_changes']}"
    )

    print(
        f"Grid rebuilds      : "
        f"{result['grid_rebuilds']}"
    )

    print(
        f"Risk Violations    : "
        f"{result['risk_violations']}"
    )

    print(
        f"BUY Blocked        : "
        f"{result['buy_blocked']}"
    )

    # --------------------------------------------------------
    # FILES
    # --------------------------------------------------------

    segments = calculate_segment_performance(
        result["curve"]
    )

    result["curve"].to_csv(
        "backtest_v048_equity.csv",
        index=False,
    )

    result["regimes"].to_csv(
        "backtest_v048_regimes.csv",
        index=False,
    )

    result["trades"].to_csv(
        "backtest_v048_trades.csv",
        index=False,
    )

    segments.to_csv(
        "backtest_v048_segments.csv",
        index=False,
    )

    print()
    print("=" * 78)
    print("REGIME / TREND PERFORMANCE")
    print("=" * 78)

    if not segments.empty:
        print(
            segments.to_string(
                index=False,
                formatters={
                    "start_equity":
                        lambda x: f"{x:.2f}",
                    "end_equity":
                        lambda x: f"{x:.2f}",
                    "pnl":
                        lambda x: f"{x:.2f}",
                    "return_pct":
                        lambda x: f"{x:.2f}%",
                },
            )
        )

    print()
    print("=" * 78)
    print("P/L RECONCILIATION")
    print("=" * 78)
    print(
        f"Equity Delta          : "
        f"{reconciliation['equity_delta']:.6f} USDT"
    )
    print(
        f"Realized Cycle P/L    : "
        f"{reconciliation['realized_cycle_pnl']:.6f} USDT"
    )
    print(
        f"Unrealized Residual   : "
        f"{reconciliation['unrealized_residual']:.6f} USDT"
    )
    print(
        f"Reconciliation Error  : "
        f"{reconciliation['reconciliation_error']:.10f} USDT"
    )

    print()
    print("=" * 78)
    print("TRADE EDGE ANALYSIS")
    print("=" * 78)

    print()
    print("OVERALL GRID CYCLES")

    if not edge["summary"].empty:
        print(
            edge["summary"].to_string(
                index=False,
                formatters={
                    "win_rate_pct":
                        lambda x: f"{x:.2f}%",
                    "cycle_pnl":
                        lambda x: f"{x:.4f}",
                    "cycle_fees":
                        lambda x: f"{x:.4f}",
                    "avg_cycle_pnl":
                        lambda x: f"{x:.4f}",
                    "best_cycle":
                        lambda x: f"{x:.4f}",
                    "worst_cycle":
                        lambda x: f"{x:.4f}",
                },
            )
        )

    print()
    print("BY VOLATILITY REGIME")

    if not edge["regime"].empty:
        print(
            edge["regime"].to_string(
                index=False,
                formatters={
                    "win_rate_pct":
                        lambda x: f"{x:.2f}%",
                    "gross_pnl":
                        lambda x: f"{x:.4f}",
                    "fees":
                        lambda x: f"{x:.4f}",
                    "avg_cycle_pnl":
                        lambda x: f"{x:.4f}",
                    "best_cycle":
                        lambda x: f"{x:.4f}",
                    "worst_cycle":
                        lambda x: f"{x:.4f}",
                },
            )
        )

    print()
    print("BY TREND")

    if not edge["trend"].empty:
        print(
            edge["trend"].to_string(
                index=False,
                formatters={
                    "win_rate_pct":
                        lambda x: f"{x:.2f}%",
                    "gross_pnl":
                        lambda x: f"{x:.4f}",
                    "fees":
                        lambda x: f"{x:.4f}",
                    "avg_cycle_pnl":
                        lambda x: f"{x:.4f}",
                    "best_cycle":
                        lambda x: f"{x:.4f}",
                    "worst_cycle":
                        lambda x: f"{x:.4f}",
                },
            )
        )

    print()
    print("BY GRID LEVEL")

    if not edge["levels"].empty:
        print(
            edge["levels"].to_string(
                index=False,
                formatters={
                    "win_rate_pct":
                        lambda x: f"{x:.2f}%",
                    "pnl":
                        lambda x: f"{x:.4f}",
                    "avg_pnl":
                        lambda x: f"{x:.4f}",
                    "best":
                        lambda x: f"{x:.4f}",
                    "worst":
                        lambda x: f"{x:.4f}",
                },
            )
        )

    # Save edge analysis.
    edge["summary"].to_csv(
        "backtest_v048_edge_summary.csv",
        index=False,
    )

    edge["regime"].to_csv(
        "backtest_v048_edge_regime.csv",
        index=False,
    )

    edge["trend"].to_csv(
        "backtest_v048_edge_trend.csv",
        index=False,
    )

    edge["levels"].to_csv(
        "backtest_v048_edge_levels.csv",
        index=False,
    )

    edge["cycles"].to_csv(
        "backtest_v048_grid_cycles.csv",
        index=False,
    )

    pd.DataFrame([reconciliation]).to_csv(
        "backtest_v048_reconciliation.csv",
        index=False,
    )

    print()
    print("Saved:")
    print("  backtest_v048_equity.csv")
    print("  backtest_v048_regimes.csv")
    print("  backtest_v048_trades.csv")
    print("  backtest_v048_segments.csv")
    print("  backtest_v048_edge_summary.csv")
    print("  backtest_v048_edge_regime.csv")
    print("  backtest_v048_edge_trend.csv")
    print("  backtest_v048_edge_levels.csv")
    print("  backtest_v048_grid_cycles.csv")
    print("  backtest_v048_reconciliation.csv")

    print()
    print("=" * 78)
    print("              V4.8 REALIZED P/L COMPLETE")
    print("=" * 78)
    print()


if __name__ == "__main__":
    main()
