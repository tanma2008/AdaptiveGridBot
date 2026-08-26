"""
Adaptive Grid Bot v5.0 - OKX DEMO Smart Loop
Candidate E:
    Grid        = 0.60%
    Order size  = 20 USDT
    SELL mult   = 2.5x

This version is compatible with the installed OKX package:
    okx 2.1.2
    python-okx 0.4.3

Important:
- Uses ONLY .env.v50
- OKX Demo flag = 1
- Read-only when V50_ENABLE_ORDERS=NO
- Demo orders when V50_ENABLE_ORDERS=YES
- Does NOT cancel existing orders
- Does NOT use TradeAPI.place_order(), because the installed SDK
  always adds stpMode='' to the request.
- Sends the minimal order params directly through the installed SDK
  request method, avoiding the empty stpMode parameter.
"""

import os
import time
import signal
from datetime import datetime, timezone

from dotenv import load_dotenv

import okx.Trade as Trade
import okx.Account as Account
import okx.MarketData as MarketData


# ============================================================
# CONFIG
# ============================================================

ENV_FILE = ".env.v50"

INST_ID = "BTC-USDT"
TD_MODE = "cash"

# Validated Candidate E
GRID_PCT = 0.0060
ORDER_USDT = 20.0
SELL_MULT = 2.5

# Safety
MAX_OPEN_ORDERS = 20
MAX_BUY_ORDERS = 10
MAX_SELL_ORDERS = 10
LOOP_SECONDS = 30

# Maximum BTC inventory value allowed for this bot's buying.
BOT_MAX_INVENTORY_USDT = 200.0

# 0.08% buy fee
# + 0.08% sell fee
# + 0.005% slippage per side
# + 0.10% safety margin
MIN_PROFIT_SPREAD = 0.0027

running = True


# ============================================================
# SIGNAL HANDLER
# ============================================================

def stop_handler(signum, frame):
    global running
    running = False
    print()
    print("Stopping v5 safely.")
    print("Existing orders are NOT cancelled.")


signal.signal(signal.SIGINT, stop_handler)
signal.signal(signal.SIGTERM, stop_handler)


# ============================================================
# ENV / FORMATTING
# ============================================================

def require_env(name):
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"{name} is missing in {ENV_FILE}"
        )

    return value


def fmt_price(price):
    return f"{price:.1f}"


def fmt_qty(qty):
    return f"{qty:.6f}"


# ============================================================
# API INITIALIZATION
# ============================================================

def api_init():
    api_key = require_env("OKX_API_KEY")
    secret = require_env("OKX_SECRET_KEY")
    passphrase = require_env("OKX_PASSPHRASE")

    # OKX Demo Trading
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


# ============================================================
# MARKET DATA
# ============================================================

def get_last_price(market):
    response = market.get_ticker(
        instId=INST_ID
    )

    if (
        response.get("code") != "0"
        or not response.get("data")
    ):
        raise RuntimeError(
            f"Ticker error: {response}"
        )

    return float(
        response["data"][0]["last"]
    )


# ============================================================
# ACCOUNT
# ============================================================

def get_balance(account):
    response = account.get_account_balance(
        ccy="USDT,BTC"
    )

    if (
        response.get("code") != "0"
        or not response.get("data")
    ):
        raise RuntimeError(
            f"Balance error: {response}"
        )

    details = response["data"][0].get(
        "details",
        []
    )

    result = {
        "USDT": 0.0,
        "BTC": 0.0,
    }

    for item in details:
        ccy = item.get("ccy")

        if ccy in result:
            result[ccy] = float(
                item.get("availBal")
                or item.get("cashBal")
                or 0
            )

    return result


# ============================================================
# ORDERS
# ============================================================

def get_pending(trade):
    response = trade.get_order_list(
        instType="SPOT"
    )

    if response.get("code") != "0":
        raise RuntimeError(
            f"Pending orders error: {response}"
        )

    orders = []

    for order in response.get(
        "data",
        []
    ):
        if order.get(
            "instId"
        ) == INST_ID:
            orders.append(order)

    return orders


def has_price(
    orders,
    side,
    price,
    tolerance=0.000001,
):
    for order in orders:
        if order.get("side") != side:
            continue

        try:
            existing_price = float(
                order.get("px", 0)
            )
        except Exception:
            continue

        if (
            abs(
                existing_price - price
            )
            / price
            <= tolerance
        ):
            return True

    return False


# ============================================================
# PLACE ORDER
# ============================================================

def place_limit(
    trade,
    side,
    price,
    usdt_size,
):
    """
    Place a spot limit order.

    IMPORTANT:
    Do NOT use trade.place_order() here.

    The installed okx 2.1.2 TradeAPI.place_order()
    always creates:

        'stpMode': ''

    in its params dictionary.

    OKX Demo rejects that empty parameter for this account
    with:

        51000 Parameter stpMode error

    Therefore we call the SDK's authenticated request method
    directly with only the required parameters.
    """

    qty = usdt_size / price

    params = {
        "instId": INST_ID,
        "tdMode": TD_MODE,
        "side": side,
        "ordType": "limit",
        "px": fmt_price(price),
        "sz": fmt_qty(qty),
    }

    try:
        response = trade._request_with_params(
            Trade.POST,
            Trade.PLACR_ORDER,
            params,
        )
    except Exception as exc:
        print(
            f"ORDER EXCEPTION "
            f"{side} {price:.1f}: "
            f"{type(exc).__name__}: {exc}"
        )
        return False

    if response.get("code") != "0":
        print(
            f"ORDER ERROR "
            f"{side} {price:.1f}: "
            f"{response}"
        )
        return False

    order_data = response.get(
        "data",
        []
    )

    order_id = ""

    if order_data:
        order_id = (
            order_data[0].get("ordId")
            or ""
        )

    print(
        f"ORDER {side:<4} "
        f"${usdt_size:7.2f} "
        f"px={price:,.1f} "
        f"qty={qty:.6f} "
        f"ordId={order_id}"
    )

    return True


# ============================================================
# GRID LEVELS
# ============================================================

def build_levels(last):
    """
    Candidate E:

        Grid       = 0.60%
        SELL mult  = 2.5x

    BUY step:
        0.60%

    SELL step:
        0.60% x 2.5
        = 1.50%
    """

    buy_step = GRID_PCT
    sell_step = GRID_PCT * SELL_MULT

    buys = []
    sells = []

    # Profit filter.
    if GRID_PCT >= MIN_PROFIT_SPREAD:
        for i in range(
            1,
            MAX_BUY_ORDERS + 1,
        ):
            buys.append(
                last
                * (
                    1.0
                    - buy_step * i
                )
            )

    for i in range(
        1,
        MAX_SELL_ORDERS + 1,
    ):
        sells.append(
            last
            * (
                1.0
                + sell_step * i
            )
        )

    return buys, sells


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 76)
    print(
        "        ADAPTIVE GRID BOT v5.0 "
        "- OKX DEMO SMART LOOP"
    )
    print("=" * 76)

    print(
        f"ENV          : {ENV_FILE}"
    )

    print(
        f"Symbol       : {INST_ID}"
    )

    print(
        f"Grid         : "
        f"{GRID_PCT * 100:.2f}%"
    )

    print(
        f"Order size   : "
        f"${ORDER_USDT:.2f}"
    )

    print(
        f"SELL mult.   : "
        f"{SELL_MULT:.2f}x"
    )

    print(
        f"Profit floor : "
        f"{MIN_PROFIT_SPREAD * 100:.2f}%"
    )

    print()

    if not os.path.exists(
        ENV_FILE
    ):
        raise RuntimeError(
            f"{ENV_FILE} not found."
        )

    # Load ONLY v5 credentials.
    load_dotenv(
        ENV_FILE,
        override=True,
    )

    enabled = (
        os.getenv(
            "V50_ENABLE_ORDERS",
            "NO",
        ).upper()
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

    print(
        "OKX API FLAG : 1 (DEMO)"
    )

    print()

    market, account, trade = api_init()

    # --------------------------------------------------------
    # Initial validation
    # --------------------------------------------------------

    last = get_last_price(
        market
    )

    balance = get_balance(
        account
    )

    pending = get_pending(
        trade
    )

    print(
        f"BTC price    : "
        f"${last:,.2f}"
    )

    print(
        f"USDT avail   : "
        f"{balance['USDT']:.4f}"
    )

    print(
        f"BTC avail    : "
        f"{balance['BTC']:.8f}"
    )

    print(
        f"V5 orders    : "
        f"{len(pending)}"
    )

    print()

    # --------------------------------------------------------
    # READ ONLY MODE
    # --------------------------------------------------------

    if not enabled:
        print(
            "READ ONLY CHECK PASSED."
        )

        print(
            "Set V50_ENABLE_ORDERS=YES "
            "in .env.v50 only when ready "
            "to place Demo orders."
        )

        return

    # --------------------------------------------------------
    # SMART LOOP
    # --------------------------------------------------------

    while running:
        try:
            last = get_last_price(
                market
            )

            balance = get_balance(
                account
            )

            pending = get_pending(
                trade
            )

            inventory_value = (
                balance["BTC"]
                * last
            )

            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"BTC={last:,.1f} "
                f"USDT={balance['USDT']:.2f} "
                f"BTC={balance['BTC']:.6f} "
                f"V5orders={len(pending)}"
            )

            # ------------------------------------------------
            # Global order limit
            # ------------------------------------------------

            if (
                len(pending)
                >= MAX_OPEN_ORDERS
            ):
                time.sleep(
                    LOOP_SECONDS
                )
                continue

            buys, sells = build_levels(
                last
            )

            # ------------------------------------------------
            # BUY
            # ------------------------------------------------

            if (
                inventory_value
                < BOT_MAX_INVENTORY_USDT
            ):
                buy_price = (
                    buys[0]
                    if buys
                    else None
                )

                if (
                    buy_price
                    and balance["USDT"]
                    >= ORDER_USDT * 1.01
                    and not has_price(
                        pending,
                        "buy",
                        buy_price,
                    )
                ):
                    place_limit(
                        trade,
                        "buy",
                        buy_price,
                        ORDER_USDT,
                    )

            # ------------------------------------------------
            # SELL
            # ------------------------------------------------

            if balance["BTC"] > 0:
                sell_price = sells[0]

                if not has_price(
                    pending,
                    "sell",
                    sell_price,
                ):
                    sell_size = min(
                        ORDER_USDT,
                        balance["BTC"]
                        * sell_price,
                    )

                    if sell_size >= 5.0:
                        place_limit(
                            trade,
                            "sell",
                            sell_price,
                            sell_size,
                        )

            time.sleep(
                LOOP_SECONDS
            )

        except KeyboardInterrupt:
            break

        except Exception as exc:
            print(
                f"LOOP ERROR: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            time.sleep(
                LOOP_SECONDS
            )

    print()
    print("V5 STOPPED.")
    print(
        "Existing V5 orders "
        "were NOT cancelled."
    )


if __name__ == "__main__":
    main()
