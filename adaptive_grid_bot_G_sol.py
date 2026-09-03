import os
import time
from decimal import Decimal, ROUND_DOWN

from dotenv import load_dotenv
import okx.Account as Account

from market_data import get_candles, candles_to_dataframe
from sol_grid_engine_v048 import (
    calculate_atr,
    calculate_position_sizing,
    determine_trend,
    evaluate_risk,
    build_grid,
    ATR_MULTIPLIER,
    GRID_LEVELS_UP,
    GRID_LEVELS_DOWN,
)
from sol_order_manager_v048 import OrderManager

load_dotenv()

INST_ID = "SOL-USDT"
INTERVAL = 60
MAX_EXPOSURE_USDT = Decimal("500.00")
DRY_RUN = "--dry-run" in os.sys.argv


def D(value):
    return Decimal(str(value))


def price_round(value):
    return D(value).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def get_live_state():
    candles_1h = get_candles(INST_ID, "1H", "500")
    candles_1d = get_candles(INST_ID, "1D", "100")
    df_1h = candles_to_dataframe(candles_1h)
    df_1d = candles_to_dataframe(candles_1d)
    if len(df_1h) < 200 or len(df_1d) < 31:
        raise RuntimeError("Insufficient candles for v4.8 EMA200 / ATR30")
    df_1h["ema50"] = df_1h["close"].ewm(span=50, adjust=False).mean()
    df_1h["ema200"] = df_1h["close"].ewm(span=200, adjust=False).mean()
    df_1d["atr30"] = calculate_atr(df_1d, 30)
    h = df_1h.iloc[-1]
    d = df_1d.iloc[-1]
    price = D(h["close"])
    ema50 = D(h["ema50"])
    ema200 = D(h["ema200"])
    atr30 = D(d["atr30"])
    trend = determine_trend(h)
    grid_distance = atr30 * D(str(ATR_MULTIPLIER))
    return price, ema50, ema200, atr30, trend, grid_distance


def account_balances():
    flag = os.getenv("OKX_FLAG", "1")
    if flag != "1":
        raise RuntimeError(f"SAFETY STOP: OKX_FLAG must be '1', got {flag!r}")
    api = Account.AccountAPI(
        api_key=os.getenv("OKX_API_KEY"),
        api_secret_key=os.getenv("OKX_SECRET_KEY"),
        passphrase=os.getenv("OKX_PASSPHRASE"),
        flag="1",
        debug=False,
    )
    response = api.get_account_balance()
    if response.get("code") != "0":
        raise RuntimeError(f"OKX DEMO Account Error: {response}")
    details = response.get("data", [{}])[0].get("details", [])
    return {x.get("ccy"): D(x.get("availBal", "0")) for x in details if x.get("ccy")}


def order_value(order):
    return D(order.get("px", "0")) * D(order.get("sz", "0"))


def matches(order, target):
    return (
        str(order.get("side", "")).lower() == target["side"].lower()
        and price_round(order.get("px", "0")) == price_round(target["price"])
    )


def reconcile(manager, target_grid, open_orders):
    used = set()
    missing = []
    stale = []
    for target in target_grid:
        found = None
        for i, existing in enumerate(open_orders):
            if i not in used and matches(existing, target):
                found = i
                break
        if found is None:
            missing.append(target)
        else:
            used.add(found)
    for i, existing in enumerate(open_orders):
        if i not in used:
            stale.append(existing)
    return stale, missing


def cancel_stale(manager, stale):
    for order in stale:
        ord_id = order.get("ordId")
        if not ord_id:
            continue
        try:
            manager.cancel_order(ord_id)
            print(f"[CANCELLED] {order.get('side','').upper():4} | ${D(order.get('px','0')):,.2f} | {ord_id}")
        except Exception as exc:
            print(f"[CANCEL FAILED] {ord_id} | {exc}")


def place_missing(manager, missing, sol_available, remaining):
    placed = 0
    blocked_sells = 0
    for target in missing:
        side = target["side"].lower()
        px = price_round(target["price"])
        if remaining < D("0.01"):
            break
        if side == "sell":
            need_sol = D("62.50") / px
            if sol_available < need_sol:
                blocked_sells += 1
                print(f"[SELL BLOCKED] Level {target['level']:>3} | need {need_sol:.6f} SOL | available {sol_available:.6f}")
                continue
        try:
            response = manager.place_limit_order(
                side=side,
                price=px,
                usdt_size=D("62.50"),
            )
            ord_id = response.get("data", [{}])[0].get("ordId", "")
            print(f"[PLACED] Level {target['level']:>3} | {side.upper():4} | ${px:,.2f} | {ord_id}")
            placed += 1
            remaining -= D("62.50")
            if side == "sell":
                sol_available -= D("62.50") / px
        except Exception as exc:
            print(f"[PLACE FAILED] Level {target['level']:>3} | {side.upper():4} | ${px:,.2f} | {exc}")
    return placed, blocked_sells


def run_cycle(cycle):
    print()
    print("=" * 76)
    print(f" SMART LOOP CYCLE {cycle} | {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 76)

    flag = os.getenv("OKX_FLAG", "1")
    if flag != "1":
        raise RuntimeError("ABORTED: OKX DEMO required (OKX_FLAG=1)")

    price, ema50, ema200, atr30, trend, grid_distance = get_live_state()
    sizing = calculate_position_sizing()
    risk = evaluate_risk(float(price), float(atr30), trend, sizing)
    if risk["status"] != "PASS":
        raise RuntimeError(f"V4.8 RISK BLOCK: {risk}")

    grid_raw = build_grid(float(price), float(grid_distance), GRID_LEVELS_UP, GRID_LEVELS_DOWN)
    target_grid = [
        {"level": int(x["level"]), "side": str(x["side"]).lower(), "price": price_round(x["price"])}
        for x in grid_raw.to_dict("records")
    ]

    balances = account_balances()
    usdt = balances.get("USDT", D("0"))
    sol = balances.get("SOL", D("0"))
    manager = OrderManager()
    open_orders = manager.get_open_orders()
    exposure = sum((order_value(x) for x in open_orders), D("0"))
    stale, missing = reconcile(manager, target_grid, open_orders)

    print(f"Price            : ${price:,.2f}")
    print(f"EMA50 / EMA200   : ${ema50:,.2f} / ${ema200:,.2f}")
    print(f"Trend            : {trend}")
    print(f"ATR30 (1D)       : ${atr30:,.2f}")
    print(f"Grid distance    : ${grid_distance:,.2f} (ATR x {ATR_MULTIPLIER})")
    print(f"Grid levels      : {GRID_LEVELS_DOWN} BUY / {GRID_LEVELS_UP} SELL")
    print(f"Order size       : $62.50 / level")
    print(f"USDT / SOL       : {usdt:,.4f} / {sol:,.6f}")
    print(f"Open orders      : {len(open_orders)}")
    print(f"Exposure         : ${exposure:,.2f} / ${MAX_EXPOSURE_USDT:,.2f}")
    print(f"Stale / Missing  : {len(stale)} / {len(missing)}")

    if exposure > MAX_EXPOSURE_USDT:
        raise RuntimeError("V4.8 SAFETY BLOCK: existing exposure exceeds $500 cap")
    if len(open_orders) > 8:
        raise RuntimeError("V4.8 SAFETY BLOCK: more than 8 open orders")

    if stale and not DRY_RUN:
        cancel_stale(manager, stale)
        open_orders = manager.get_open_orders()
        exposure = sum((order_value(x) for x in open_orders), D("0"))

    if DRY_RUN:
        print("DRY RUN         : no cancel/place operations")
        return

    remaining = MAX_EXPOSURE_USDT - exposure
    if remaining < 0:
        remaining = D("0")
    placed, blocked = place_missing(manager, missing, sol, remaining)

    final_orders = manager.get_open_orders()
    buys = sum(1 for x in final_orders if str(x.get("side", "")).lower() == "buy")
    sells = sum(1 for x in final_orders if str(x.get("side", "")).lower() == "sell")
    final_exposure = sum((order_value(x) for x in final_orders), D("0"))
    print(f"RESULT           : placed={placed} sell_blocked={blocked} open={len(final_orders)} BUY={buys} SELL={sells} exposure=${final_exposure:,.2f}")
    return


def main():
    print()
    print("=" * 76)
    print("      ADAPTIVE GRID BOT G | SOL-USDT v4.8")
    print("      .env | OKX DEMO | ORIGINAL v4.8 ALGORITHM")
    print("=" * 76)
    print("Check interval : 60 seconds")
    print("Mode           : OKX DEMO ONLY")
    print("Algorithm      : EMA50/200 + ATR30D + ATR x 0.3")
    print("Grid           : 5 BUY / 3 SELL")
    print("Capital        : $1,000")
    print("Max exposure   : $500")
    print("Order size     : $62.50 / level")
    print("Ctrl+C         : STOP")
    print("=" * 76)
    cycle = 0
    once = "--once" in os.sys.argv
    while True:
        cycle += 1
        try:
            run_cycle(cycle)
            if once:
                break
        except KeyboardInterrupt:
            print("\nG v4.8 STOPPED. Existing OKX DEMO orders were left untouched.")
            break
        except Exception as exc:
            print(f"[LOOP ERROR] {type(exc).__name__}: {exc}")
            print("No emergency cancel-all will be performed.")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
