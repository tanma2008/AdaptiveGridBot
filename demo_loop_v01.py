import csv
import os
import time
from datetime import datetime
from decimal import Decimal, ROUND_DOWN

from dotenv import load_dotenv
import okx.MarketData as MarketData

from order_manager import OrderManager


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

INST_ID = "BTC-USDT"

CHECK_INTERVAL = 10

STRATEGY_CAPITAL = Decimal("100")
MAX_EXPOSURE = Decimal("30")

ORDER_SIZE_USDT = Decimal("5")

GRID_PERCENT = Decimal("0.001")   # 0.10%

MAX_OPEN_ORDERS = 1

MAX_CYCLES = 20

LOG_FILE = "demo_loop_v01.csv"


# ============================================================
# OKX MARKET
# ============================================================

FLAG = os.getenv("OKX_FLAG", "1")

market_api = MarketData.MarketAPI(
    flag=FLAG
)


# ============================================================
# HELPERS
# ============================================================

def now():

    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def get_price():

    response = market_api.get_ticker(
        instId=INST_ID
    )

    if response.get("code") != "0":

        raise RuntimeError(
            f"Market error: {response}"
        )

    return Decimal(
        response["data"][0]["last"]
    )


def write_log(
    event,
    side="",
    price="",
    size="",
    pnl="",
    order_id="",
):

    exists = os.path.exists(
        LOG_FILE
    )

    with open(
        LOG_FILE,
        "a",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.writer(f)

        if not exists:

            writer.writerow([
                "time",
                "event",
                "side",
                "price",
                "size",
                "pnl",
                "order_id",
            ])

        writer.writerow([
            now(),
            event,
            side,
            price,
            size,
            pnl,
            order_id,
        ])


# ============================================================
# ROUND BTC SIZE
# ============================================================

def btc_size_from_usdt(
    usdt,
    price,
):

    size = usdt / price

    return size.quantize(
        Decimal("0.000001"),
        rounding=ROUND_DOWN,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 72)
    print("       ADAPTIVE GRID BOT - DEMO LOOP V0.1")
    print("=" * 72)

    print()
    print("Purpose       : ENGINE TEST")
    print("Exchange      : OKX DEMO")
    print("Symbol        :", INST_ID)
    print()
    print(
        f"Strategy Cap  : "
        f"{STRATEGY_CAPITAL:.2f} USDT"
    )
    print(
        f"Max Exposure  : "
        f"{MAX_EXPOSURE:.2f} USDT"
    )
    print(
        f"Order Size    : "
        f"{ORDER_SIZE_USDT:.2f} USDT"
    )
    print(
        f"Grid Distance : "
        f"{GRID_PERCENT * 100:.2f}%"
    )
    print(
        f"Max Cycles    : "
        f"{MAX_CYCLES}"
    )

    print()
    print("SAFETY")
    print("-" * 72)
    print("Spot only")
    print("No leverage")
    print("One active order")
    print("No martingale")
    print("Demo only")
    print()

    manager = OrderManager()

    cycle = 0

    position_btc = Decimal("0")
    buy_price = Decimal("0")

    while cycle < MAX_CYCLES:

        try:

            # =================================================
            # CHECK EXISTING ORDERS
            # =================================================

            orders = (
                manager.get_open_orders()
            )

            if len(orders) > MAX_OPEN_ORDERS:

                print()
                print(
                    "🛑 KILL SWITCH"
                )

                print(
                    "Too many open orders."
                )

                break

            # =================================================
            # IF ORDER EXISTS
            # =================================================

            if orders:

                order = orders[0]

                ord_id = order.get(
                    "ordId"
                )

                state = order.get(
                    "state"
                )

                print(
                    f"[{now()}] "
                    f"ORDER {ord_id} "
                    f"STATE={state}"
                )

                # ------------------------------------------------
                # Check whether order has filled
                # ------------------------------------------------

                details = (
                    manager.get_order_details(
                        ord_id
                    )
                )

                state = details.get(
                    "state"
                )

                if state == "filled":

                    side = details.get(
                        "side"
                    )

                    filled = Decimal(
                        details.get(
                            "accFillSz",
                            "0"
                        )
                    )

                    avg_px = Decimal(
                        details.get(
                            "avgPx",
                            "0"
                        ) or "0"
                    )

                    print()
                    print(
                        "=" * 72
                    )

                    print(
                        "🟢 FILLED"
                    )

                    print(
                        f"Side   : {side}"
                    )

                    print(
                        f"BTC    : {filled}"
                    )

                    print(
                        f"Price  : {avg_px}"
                    )

                    print(
                        "=" * 72
                    )

                    # ------------------------------------------------
                    # BUY FILLED
                    # ------------------------------------------------

                    if side == "buy":

                        position_btc = filled

                        buy_price = avg_px

                        sell_price = (
                            buy_price
                            * (
                                Decimal("1")
                                + GRID_PERCENT
                            )
                        )

                        sell_value = (
                            position_btc
                            * sell_price
                        )

                        print()
                        print(
                            "Creating SELL..."
                        )

                        print(
                            f"SELL Price : "
                            f"{sell_price:.2f}"
                        )

                        print(
                            f"BTC        : "
                            f"{position_btc}"
                        )

                        response = (
                            manager.place_limit_order(
                                side="sell",
                                price=sell_price,
                                usdt_size=sell_value,
                            )
                        )

                        sell_order_id = (
                            response
                            .get("data", [{}])[0]
                            .get("ordId", "")
                        )

                        print(
                            f"SELL Order : "
                            f"{sell_order_id}"
                        )

                        write_log(
                            "BUY_FILLED",
                            "buy",
                            str(avg_px),
                            str(filled),
                            "",
                            ord_id,
                        )

                        write_log(
                            "SELL_CREATED",
                            "sell",
                            str(sell_price),
                            str(position_btc),
                            "",
                            sell_order_id,
                        )

                    # ------------------------------------------------
                    # SELL FILLED
                    # ------------------------------------------------

                    elif side == "sell":

                        sell_price = avg_px

                        pnl = (
                            (
                                sell_price
                                - buy_price
                            )
                            * position_btc
                        )

                        print()
                        print(
                            "💰 CYCLE COMPLETE"
                        )

                        print(
                            f"BUY  : "
                            f"{buy_price:.2f}"
                        )

                        print(
                            f"SELL : "
                            f"{sell_price:.2f}"
                        )

                        print(
                            f"Gross P/L : "
                            f"{pnl:.6f} USDT"
                        )

                        write_log(
                            "SELL_FILLED",
                            "sell",
                            str(sell_price),
                            str(position_btc),
                            str(pnl),
                            ord_id,
                        )

                        position_btc = (
                            Decimal("0")
                        )

                        buy_price = (
                            Decimal("0")
                        )

                        cycle += 1

                        print(
                            f"Cycle : "
                            f"{cycle}/{MAX_CYCLES}"
                        )

                    time.sleep(
                        CHECK_INTERVAL
                    )

                    continue

                time.sleep(
                    CHECK_INTERVAL
                )

                continue

            # =================================================
            # NO OPEN ORDER
            # =================================================

            price = get_price()

            print()
            print(
                "=" * 72
            )

            print(
                f"[{now()}] "
                f"BTC ${price:,.2f}"
            )

            # ------------------------------------------------
            # Exposure safety
            # ------------------------------------------------

            if ORDER_SIZE_USDT > MAX_EXPOSURE:

                print(
                    "🛑 KILL SWITCH"
                )

                print(
                    "Order exceeds exposure."
                )

                break

            # ------------------------------------------------
            # TEST BUY
            # ------------------------------------------------

            buy_price = (
                price
                * (
                    Decimal("1")
                    - GRID_PERCENT
                )
            )

            btc_size = (
                btc_size_from_usdt(
                    ORDER_SIZE_USDT,
                    buy_price,
                )
            )

            if btc_size <= 0:

                print(
                    "Order size too small."
                )

                break

            print()
            print(
                "Creating TEST BUY"
            )

            print(
                f"Price : "
                f"${buy_price:,.2f}"
            )

            print(
                f"Size  : "
                f"{ORDER_SIZE_USDT:.2f} USDT"
            )

            response = (
                manager.place_limit_order(
                    side="buy",
                    price=buy_price,
                    usdt_size=ORDER_SIZE_USDT,
                )
            )

            order_id = (
                response
                .get("data", [{}])[0]
                .get("ordId", "")
            )

            print(
                f"Order ID : "
                f"{order_id}"
            )

            write_log(
                "BUY_CREATED",
                "buy",
                str(buy_price),
                str(btc_size),
                "",
                order_id,
            )

            time.sleep(
                CHECK_INTERVAL
            )

        except KeyboardInterrupt:

            print()
            print(
                "Bot stopped manually."
            )

            break

        except Exception as e:

            print()
            print(
                "ERROR:"
            )

            print(
                repr(e)
            )

            print(
                "Retrying..."
            )

            time.sleep(
                CHECK_INTERVAL
            )

    print()
    print("=" * 72)
    print("             TEST LOOP STOPPED")
    print("=" * 72)
    print(
        f"Completed cycles : {cycle}"
    )
    print(
        f"Log file         : {LOG_FILE}"
    )
    print()


if __name__ == "__main__":

    main()