from decimal import Decimal

STRATEGY_CAPITAL_USDT = Decimal("1000.00")
MAX_EXPOSURE_USDT = Decimal("500.00")
GRID_LEVELS = 8


def calculate_position_sizing(strategy_capital=STRATEGY_CAPITAL_USDT, max_exposure=MAX_EXPOSURE_USDT, grid_levels=GRID_LEVELS):
    strategy_capital = Decimal(str(strategy_capital))
    max_exposure = Decimal(str(max_exposure))
    if strategy_capital <= 0 or max_exposure <= 0 or grid_levels <= 0:
        raise ValueError("Invalid position sizing configuration")
    usable = min(strategy_capital, max_exposure)
    return {"strategy_capital_usdt": strategy_capital, "max_exposure_usdt": max_exposure, "usable_capital_usdt": usable, "grid_levels": grid_levels, "order_size_usdt": usable / Decimal(grid_levels)}
