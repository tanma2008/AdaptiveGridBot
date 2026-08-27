from decimal import Decimal

MAX_EXPOSURE_USDT = Decimal("500.00")
MAX_ATR_PERCENT = Decimal("0.25")


def evaluate_risk(price, atr30, strategy_capital, max_exposure=MAX_EXPOSURE_USDT, trend="SIDEWAY"):
    price = Decimal(str(price)); atr30 = Decimal(str(atr30)); strategy_capital = Decimal(str(strategy_capital)); max_exposure = Decimal(str(max_exposure))
    checks = {"price_positive": price > 0, "atr_positive": atr30 > 0, "capital_positive": strategy_capital > 0, "exposure_within_cap": max_exposure <= strategy_capital, "atr_percent_safe": price > 0 and Decimal("0") < atr30 / price < MAX_ATR_PERCENT, "trend_valid": trend in {"UP", "DOWN", "SIDEWAY"}}
    return {"status": "PASS" if all(checks.values()) else "BLOCK", "atr_percent": atr30 / price if price > 0 else Decimal("0"), "checks": checks}
