import pandas as pd

FILE_1H = "sol_usdt_1h.csv"
FILE_1D = "sol_usdt_1d.csv"
ATR_MULTIPLIER = 0.3
GRID_LEVELS_UP = 3
GRID_LEVELS_DOWN = 5
STRATEGY_CAPITAL_USDT = 1000.0
MAX_EXPOSURE_USDT = 500.0


def calculate_ema(df, period):
    return df["close"].ewm(span=period, adjust=False).mean()


def calculate_true_range(df):
    previous_close = df["close"].shift(1)
    return pd.concat([df["high"] - df["low"], (df["high"] - previous_close).abs(), (df["low"] - previous_close).abs()], axis=1).max(axis=1)


def calculate_atr(df, period=30):
    return calculate_true_range(df).ewm(alpha=1 / period, adjust=False).mean()


def determine_trend(row):
    if row["close"] > row["ema50"] > row["ema200"]:
        return "UP"
    if row["close"] < row["ema50"] < row["ema200"]:
        return "DOWN"
    return "SIDEWAY"


def build_grid(price, grid_distance, levels_up=GRID_LEVELS_UP, levels_down=GRID_LEVELS_DOWN):
    grid = []
    for level in range(1, levels_down + 1):
        grid.append({"level": -level, "side": "BUY", "price": price - grid_distance * level})
    for level in range(1, levels_up + 1):
        grid.append({"level": level, "side": "SELL", "price": price + grid_distance * level})
    return pd.DataFrame(grid)


def calculate_position_sizing(strategy_capital=STRATEGY_CAPITAL_USDT, max_exposure=MAX_EXPOSURE_USDT):
    levels = GRID_LEVELS_UP + GRID_LEVELS_DOWN
    usable = min(strategy_capital, max_exposure)
    if usable <= 0:
        raise ValueError("Invalid position sizing configuration")
    return {"strategy_capital_usdt": strategy_capital, "max_exposure_usdt": max_exposure, "usable_capital_usdt": usable, "total_grid_levels": levels, "order_size_usdt": usable / levels}


def evaluate_risk(price, atr30, trend, sizing):
    atr_percent = atr30 / price if price > 0 else 0
    checks = {"price_positive": price > 0, "atr_positive": atr30 > 0, "capital_positive": sizing["strategy_capital_usdt"] > 0, "exposure_within_cap": sizing["usable_capital_usdt"] <= sizing["max_exposure_usdt"], "atr_percent_safe": 0 < atr_percent < 0.25, "trend_valid": trend in {"UP", "DOWN", "SIDEWAY"}}
    return {"status": "PASS" if all(checks.values()) else "BLOCK", "atr_percent": atr_percent, "checks": checks}


def main():
    print("=" * 76)
    print("        ADAPTIVE GRID BOT v4.8 - SOL/USDT")
    print("             READ ONLY - NO ORDERS")
    print("=" * 76)
    df_1h = pd.read_csv(FILE_1H, parse_dates=["timestamp"])
    df_1d = pd.read_csv(FILE_1D, parse_dates=["timestamp"])
    if len(df_1h) < 200 or len(df_1d) < 31:
        raise RuntimeError("Insufficient historical data for EMA200 / ATR30D")
    df_1h["ema50"] = calculate_ema(df_1h, 50)
    df_1h["ema200"] = calculate_ema(df_1h, 200)
    df_1d["atr30"] = calculate_atr(df_1d, 30)
    latest_1h = df_1h.iloc[-1]
    latest_1d = df_1d.iloc[-1]
    price = float(latest_1h["close"])
    ema50 = float(latest_1h["ema50"])
    ema200 = float(latest_1h["ema200"])
    atr30 = float(latest_1d["atr30"])
    trend = determine_trend(latest_1h)
    grid_distance = atr30 * ATR_MULTIPLIER
    grid = build_grid(price, grid_distance)
    sizing = calculate_position_sizing()
    risk = evaluate_risk(price, atr30, trend, sizing)
    print(f"SOL Price       : ${price:,.2f}")
    print(f"EMA50 (1H)      : ${ema50:,.2f}")
    print(f"EMA200 (1H)     : ${ema200:,.2f}")
    print(f"Trend           : {trend}")
    print(f"ATR30 (1D)      : ${atr30:,.2f}")
    print(f"Grid Distance   : ${grid_distance:,.2f}")
    print(f"Order Size      : ${sizing['order_size_usdt']:,.2f} / level")
    print(f"Risk Status     : {risk['status']}")
    print(f"ATR / Price     : {risk['atr_percent'] * 100:.4f}%")
    print()
    print(grid[["level", "side", "price"]].to_string(index=False, formatters={"price": lambda x: f"${x:,.2f}"}))
    print()
    print("SOL v4.8 RISK ENGINE: PASS" if risk["status"] == "PASS" else "SOL v4.8 RISK ENGINE: BLOCK")


if __name__ == "__main__":
    main()
