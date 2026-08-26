"""
ADAPTIVE GRID BOT v5.1 - OKX DEMO PERSISTENT GRID

Candidate E:
    Grid       : 0.60%
    Order size : $20
    SELL mult  : 2.50x
    Profit floor: 0.27%

Design:
- Persistent grid levels: current price does NOT move existing levels.
- One order per level.
- Refreshes OKX open orders after every successful placement.
- Uses a stable grid anchor during the process.
- Uses only .env.v50.
- OKX Demo flag = 1.
- READ ONLY unless V50_ENABLE_ORDERS=YES.
- Never cancels existing orders automatically.
- Direct authenticated request avoids SDK place_order() empty stpMode bug.
"""

import os
import time
import signal
from datetime import datetime

from dotenv import load_dotenv

import okx.Trade as Trade
import okx.Account as Account
import okx.MarketData as MarketData


ENV_FILE = ".env.v50"
INST_ID = "BTC-USDT"
TD_MODE = "cash"

GRID_PCT = 0.0060
ORDER_USDT = 20.0
SELL_MULT = 2.5
SELL_STEP = GRID_PCT * SELL_MULT

MIN_PROFIT_SPREAD = 0.0027

LOOP_SECONDS = 30

# Keep this conservative for first Demo run.
MAX_OPEN_ORDERS = 10
MAX_BUY_ORDERS = 5
MAX_SELL_ORDERS = 5

# Only orders belonging to this bot are counted/managed.
PREFIX = "V51"

running = True


def stop_handler(signum, frame):
    global running
    running = False
    print()
    print("Stopping v5.1 safely.")
    print("Existing orders are NOT cancelled.")


signal.signal(signal.SIGINT, stop_handler)
signal.signal(signal.SIGTERM, stop_handler)


def require_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is missing in {ENV_FILE}")
    return value


def fmt_price(price):
    return f"{price:.1f}"


def fmt_qty(qty):
    return f"{qty:.6f}"


def api_init():
    api_key = require_env("OKX_API_KEY")
    secret = require_env("OKX_SECRET_KEY")
    passphrase = require_env("OKX_PASSPHRASE")

    flag = "1"

    market = MarketData.MarketAPI(
        api_key,
        secret,
        passphrase,
        False,
        flag,
    )

    account = Account.AccountAPI(
        api_key,
        secret,
        passphrase,
        False,
        flag,
    )

    trade = Trade.TradeAPI(
        api_key,
        secret,
        passphrase,
        False,
        flag,
    )

    return market, account, trade


def get_last_price(market):
    r = market.get_ticker(instId=INST_ID)

    if r.get("code") != "0" or not r.get("data"):
        raise RuntimeError(f"Ticker error: {r}")

    return float(r["data"][0]["last"])


def get_balance(account):
    r = account.get_account_balance(ccy="USDT,BTC")

    if r.get("code") != "0" or not r.get("data"):
        raise RuntimeError(f"Balance error: {r}")

    result = {"USDT": 0.0, "BTC": 0.0}

    for item in r["data"][0].get("details", []):
        ccy = item.get("ccy")
        if ccy in result:
            result[ccy] = float(
                item.get("availBal")
                or item.get("cashBal")
                or 0
            )

    return result


def get_open_orders(trade):
    r = trade.get_order_list(instType="SPOT")

    if r.get("code") != "0":
        raise RuntimeError(f"Open order error: {r}")

    return [
        o for o in r.get("data", [])
        if o.get("instId") == INST_ID
    ]


def is_bot_order(order):
    clid = str(order.get("clOrdId") or "")
    tag = str(order.get("tag") or "")
    return clid.startswith(PREFIX) or tag == PREFIX


def bot_orders(orders):
    return [o for o in orders if is_bot_order(o)]


def order_price(order):
    try:
        return float(order.get("px", 0))
    except Exception:
        return 0.0


def order_side(order):
    return str(order.get("side") or "").lower()


def has_level(orders, side, price, tolerance=0.00001):
    for o in bot_orders(orders):
        if order_side(o) != side:
            continue

        p = order_price(o)
        if p <= 0:
            continue

        if abs(p - price) / price <= tolerance:
            return True

    return False


def make_clordid(side, level_index):
    # Keep under OKX client order id length limits.
    return f"{PREFIX}{side[0].upper()}{level_index:02d}"


def place_limit(trade, side, price, usdt_size, level_index):
    qty = usdt_size / price
    clid = make_clordid(side, level_index)

    params = {
        "instId": INST_ID,
        "tdMode": TD_MODE,
        "side": side,
        "ordType": "limit",
        "clOrdId": clid,
        "px": fmt_price(price),
        "sz": fmt_qty(qty),
    }

    try:
        r = trade._request_with_params(
            Trade.POST,
            Trade.PLACR_ORDER,
            params,
        )
    except Exception as exc:
        print(
            f"ORDER EXCEPTION {side} "
            f"{price:.1f}: {type(exc).__name__}: {exc}"
        )
        return False

    if r.get("code") != "0":
        print(
            f"ORDER ERROR {side} {price:.1f}: {r}"
        )
        return False

    data = r.get("data") or []
    ord_id = data[0].get("ordId", "") if data else ""

    print(
        f"ORDER {side:<4} "
        f"${usdt_size:7.2f} "
        f"px={price:,.1f} "
        f"qty={qty:.6f} "
        f"level={level_index} "
        f"clOrdId={clid} "
        f"ordId={ord_id}"
    )

    return True


def build_grid(anchor):
    buys = []
    sells = []

    for i in range(1, MAX_BUY_ORDERS + 1):
        buys.append(
            (
                i,
                anchor * (1.0 - GRID_PCT * i)
            )
        )

    for i in range(1, MAX_SELL_ORDERS + 1):
        sells.append(
            (
                i,
                anchor * (1.0 + SELL_STEP * i)
            )
        )

    return buys, sells


def main():
    print("=" * 76)
    print("       ADAPTIVE GRID BOT v5.1 - OKX DEMO PERSISTENT GRID")
    print("=" * 76)
    print(f"ENV          : {ENV_FILE}")
    print(f"Symbol       : {INST_ID}")
    print(f"Grid         : {GRID_PCT * 100:.2f}%")
    print(f"Order size   : ${ORDER_USDT:.2f}")
    print(f"SELL mult.   : {SELL_MULT:.2f}x")
    print(f"Profit floor : {MIN_PROFIT_SPREAD * 100:.2f}%")
    print(f"Prefix       : {PREFIX}")
    print()

    if not os.path.exists(ENV_FILE):
        raise RuntimeError(f"{ENV_FILE} not found")

    load_dotenv(ENV_FILE, override=True)

    enabled = (
        os.getenv("V50_ENABLE_ORDERS", "NO").upper()
        == "YES"
    )

    print(
        "ORDER MODE   : "
        + (
            "DEMO ORDERS ENABLED"
            if enabled
            else "READ ONLY"
        )
    )
    print("OKX API FLAG : 1 (DEMO)")
    print()

    market, account, trade = api_init()

    last = get_last_price(market)
    balance = get_balance(account)
    all_orders = get_open_orders(trade)
    ours = bot_orders(all_orders)

    print(f"BTC price    : ${last:,.2f}")
    print(f"USDT avail   : {balance['USDT']:.4f}")
    print(f"BTC avail    : {balance['BTC']:.8f}")
    print(f"All SPOT orders: {len(all_orders)}")
    print(f"V5.1 orders   : {len(ours)}")
    print()

    if not enabled:
        print("READ ONLY CHECK PASSED.")
        print(
            "Set V50_ENABLE_ORDERS=YES in .env.v50 "
            "only when ready to place Demo orders."
        )
        return

    # Persistent anchor:
    # If V5.1 orders already exist, keep their nearest grid reference.
    # Otherwise anchor once at startup and do NOT move it every loop.
    anchor = last

    if ours:
        prices = [
            order_price(o)
            for o in ours
            if order_price(o) > 0
        ]

        if prices:
            anchor = sum(prices) / len(prices)

    print(f"GRID ANCHOR  : ${anchor:,.1f}")
    print(
        f"BUY levels   : "
        f"{anchor * (1-GRID_PCT):,.1f} ... "
        f"{anchor * (1-GRID_PCT*MAX_BUY_ORDERS):,.1f}"
    )
    print(
        f"SELL levels  : "
        f"{anchor * (1+SELL_STEP):,.1f} ... "
        f"{anchor * (1+SELL_STEP*MAX_SELL_ORDERS):,.1f}"
    )
    print()

    buys, sells = build_grid(anchor)

    while running:
        try:
            last = get_last_price(market)
            balance = get_balance(account)

            # ALWAYS refresh from OKX before deciding what to place.
            all_orders = get_open_orders(trade)
            ours = bot_orders(all_orders)

            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"BTC={last:,.1f} "
                f"USDT={balance['USDT']:.2f} "
                f"BTC={balance['BTC']:.6f} "
                f"V5.1orders={len(ours)}"
            )

            if len(ours) >= MAX_OPEN_ORDERS:
                time.sleep(LOOP_SECONDS)
                continue

            # --------------------------------------------------
            # SELL SIDE
            # --------------------------------------------------
            # Use existing BTC as inventory reserve.
            # Only place one order per persistent level.
            for level, price in sells:
                if not running:
                    break

                # Don't create another order if this level exists.
                if has_level(
                    all_orders,
                    "sell",
                    price,
                ):
                    continue

                # Need enough BTC to cover the order.
                qty = ORDER_USDT / price

                if balance["BTC"] < qty:
                    break

                if place_limit(
                    trade,
                    "sell",
                    price,
                    ORDER_USDT,
                    level,
                ):
                    # CRITICAL: refresh immediately.
                    all_orders = get_open_orders(trade)
                    ours = bot_orders(all_orders)

                    if len(ours) >= MAX_OPEN_ORDERS:
                        break

                    # Update local balance so we don't reserve
                    # the same BTC twice in one pass.
                    balance["BTC"] -= qty

            # --------------------------------------------------
            # BUY SIDE
            # --------------------------------------------------
            # Only buy if enough USDT is available.
            for level, price in buys:
                if not running:
                    break

                if len(ours) >= MAX_OPEN_ORDERS:
                    break

                if has_level(
                    all_orders,
                    "buy",
                    price,
                ):
                    continue

                if balance["USDT"] < ORDER_USDT:
                    break

                if place_limit(
                    trade,
                    "buy",
                    price,
                    ORDER_USDT,
                    level,
                ):
                    # CRITICAL: refresh immediately.
                    all_orders = get_open_orders(trade)
                    ours = bot_orders(all_orders)

                    balance["USDT"] -= ORDER_USDT

            time.sleep(LOOP_SECONDS)

        except KeyboardInterrupt:
            break

        except Exception as exc:
            print(
                f"LOOP ERROR: {type(exc).__name__}: {exc}"
            )
            time.sleep(LOOP_SECONDS)

    print()
    print("V5.1 STOPPED.")
    print("Existing orders were NOT cancelled.")


if __name__ == "__main__":
    main()
