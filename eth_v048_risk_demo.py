from eth_risk_engine_v048 import evaluate_risk
from eth_position_sizing_v048 import calculate_position_sizing

price = 2500.46
atr30 = 76.60
trend = "UP"
sizing = calculate_position_sizing()
result = evaluate_risk(price, atr30, sizing["strategy_capital_usdt"], sizing["max_exposure_usdt"], trend)

print("ETH v4.8 RISK ENGINE - READ ONLY")
print(f"Risk Status : {result['status']}")
print(f"ATR/Price   : {result['atr_percent'] * 100:.4f}%")
for name, passed in result["checks"].items():
    print(f"{'PASS' if passed else 'BLOCK':5} | {name}")
assert result["status"] == "PASS"
print("RISK ENGINE TEST: PASS")
