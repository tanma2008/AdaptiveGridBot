from eth_risk_engine_v048 import evaluate_risk

result = evaluate_risk(
    price=2500.46,
    atr30=76.60,
    strategy_capital=1000,
    trend="UP",
)

assert result["status"] == "PASS"
assert result["checks"]["price_positive"]
assert result["checks"]["atr_positive"]
assert result["checks"]["capital_positive"]
assert result["checks"]["exposure_within_cap"]
assert result["checks"]["atr_percent_safe"]
assert result["checks"]["trend_valid"]

print("ETH v4.8 RISK ENGINE TEST: PASS")
