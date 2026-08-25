import os
import time
import csv
from decimal import Decimal, ROUND_DOWN
from datetime import datetime

from dotenv import load_dotenv
import okx.MarketData as MarketData
import okx.Account as Account

from order_manager import OrderManager


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

INST_ID = "BTC-USDT"
FLAG = os.getenv("OKX_FLAG", "1")

CHECK_INTERVAL = 10

ORDER_SIZE_USDT = Decimal("5.00")

MAX_EXPOSURE = Decimal("50.00")

GRID_PERCENT = Decimal("0.0005")     # 0.05%

BUY_LEVELS = 10
SELL_LEVELS = 10

MAX_CYCLES = 100

LOG_FILE = "grid_v03.csv"


# ============================================================
# API
# ============================================================

market_api = MarketData.MarketAPI(
    flag=FLAG
)

account_api = Account.AccountAPI(
    api_key=os.getenv("OKX_API_KEY"),
    api_secret_key=os.getenv("OKX_SECRET_KEY"),
    passphrase=os.getenv("OKX_PASSPHRASE"),
    flag=FLAG,
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
        raise RuntimeError(response)

    return Decimal(
        response["data"][0]["last"]
    )


def get_btc_balance():

    response = account_api.get_account_balance()

    if response.get("code") != "0":
        raise RuntimeError(response)

    btc = Decimal("0")

    data = response.get("data", [])

    if not data:
        return btc

    for item in data[0].get("details", []):

        if item.get("ccy") == "BTC":

            btc = Decimal(
                item.get("availBal", "0")
            )

            break

    return btc


def round_price(price):

    return price.quantize(
        Decimal("0.1"),
        rounding=ROUND_DOWN
    )


def btc_for_order(price):

    return (
        ORDER_SIZE_USDT / price
    )


def log_event(
    event,
    side="",
    level="",
    price="",
    size="",
    order_id="",
):

    exists = os.path.exists(LOG_FILE)

    with open(
        LOG_FILE,
        "a",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.writer(f)

        if not exists:

            writer.writerow([
                "time",
                "event",
                "side",
                "level",
                "price",
                "size",
                "order_id",
            ])

        writer.writerow([
            now(),
            event,
            side,
            level,
            price,
            size,
            order_id,
        ])


# ============================================================
# GRID BOT V0.3
# ============================================================

class GridBotV03:

    def __init__(self):

        self.manager = OrderManager()

        self.orders = {}

        self.cycles = 0

    # --------------------------------------------------------
    # LOAD EXISTING ORDERS
    # --------------------------------------------------------

    def load_existing_orders(self):

        orders = (
            self.manager.get_open_orders()
        )

        print(
            f"Existing OKX Orders : "
            f"{len(orders)}"
        )

        for order in orders:

            ord_id = order.get("ordId")

            self.orders[ord_id] = {
                "side": order.get("side"),
                "price": Decimal(
                    order.get("px", "0")
                ),
                "size": Decimal(
                    order.get("sz", "0")
                ),
                "level": "",
            }

    # --------------------------------------------------------
    # BUY GRID
    # --------------------------------------------------------

    def create_buy_grid(self, price):

        print()
        print(
            "BUY GRID - 10 LEVELS"
        )
        print("-" * 72)

        for level in range(
            1,
            BUY_LEVELS + 1
        ):

            grid_price = (
                price
                * (
                    Decimal("1")
                    - (
                        GRID_PERCENT
                        * level
                    )
                )
            )

            grid_price = round_price(
                grid_price
            )

            print(
                f"BUY {level:2d} "
                f"| ${grid_price:,.1f} "
                f"| {ORDER_SIZE_USDT:.2f} USDT"
            )

            try:

                response = (
                    self.manager.place_limit_order(
                        side="buy",
                        price=grid_price,
                        usdt_size=ORDER_SIZE_USDT,
                    )
                )

                data = response.get(
                    "data",
                    []
                )

                if not data:
                    print("  ERROR: no order ID")
                    continue

                ord_id = data[0].get(
                    "ordId",
                    ""
                )

                self.orders[ord_id] = {
                    "side": "buy",
                    "price": grid_price,
                    "size": (
                        ORDER_SIZE_USDT
                        / grid_price
                    ),
                    "level": level,
                }

                log_event(
                    "BUY_CREATED",
                    "buy",
                    level,
                    str(grid_price),
                    str(
                        ORDER_SIZE_USDT
                    ),
                    ord_id,
                )

            except Exception as e:

                print(
                    f"  BUY ERROR: {e}"
                )

    # --------------------------------------------------------
    # SELL GRID
    # --------------------------------------------------------

    def create_sell_grid(self, price):

        print()
        print(
            "SELL GRID - 10 LEVELS"
        )
        print("-" * 72)

        try:

            btc = get_btc_balance()

        except Exception as e:

            print(
                "BTC BALANCE ERROR:"
            )

            print(
                repr(e)
            )

            return

        print(
            f"Available BTC : "
            f"{btc}"
        )

        btc_per_order = (
            ORDER_SIZE_USDT / price
        )

        max_orders = int(
            btc / btc_per_order
        )

        max_orders = min(
            max_orders,
            SELL_LEVELS
        )

        print(
            f"SELL Capacity : "
            f"{max_orders} / {SELL_LEVELS}"
        )

        if max_orders <= 0:

            print(
                "No BTC available."
            )

            print(
                "SELL GRID SKIPPED."
            )

            return

        for level in range(
            1,
            max_orders + 1
        ):

            grid_price = (
                price
                * (
                    Decimal("1")
                    + (
                        GRID_PERCENT
                        * level
                    )
                )
            )

            grid_price = round_price(
                grid_price
            )

            print(
                f"SELL {level:2d} "
                f"| ${grid_price:,.1f} "
                f"| {ORDER_SIZE_USDT:.2f} USDT"
            )

            try:

                response = (
                    self.manager.place_limit_order(
                        side="sell",
                        price=grid_price,
                        usdt_size=ORDER_SIZE_USDT,
                    )
                )

                data = response.get(
                    "data",
                    []
                )

                if not data:
                    continue

                ord_id = data[0].get(
                    "ordId",
                    ""
                )

                self.orders[ord_id] = {
                    "side": "sell",
                    "price": grid_price,
                    "size": (
                        ORDER_SIZE_USDT
                        / grid_price
                    ),
                    "level": level,
                }

                log_event(
                    "SELL_CREATED",
                    "sell",
                    level,
                    str(grid_price),
                    str(
                        ORDER_SIZE_USDT
                    ),
                    ord_id,
                )

            except Exception as e:

                print(
                    f"  SELL ERROR: {e}"
                )

    # --------------------------------------------------------
    # CREATE OPPOSITE AFTER FILL
    # --------------------------------------------------------

    def create_opposite(
        self,
        side,
        filled_price,
        filled_size,
        level,
    ):

        if side == "buy":

            new_side = "sell"

            new_price = (
                filled_price
                * (
                    Decimal("1")
                    + GRID_PERCENT
                )
            )

        else:

            new_side = "buy"

            new_price = (
                filled_price
                * (
                    Decimal("1")
                    - GRID_PERCENT
                )
            )

        new_price = round_price(
            new_price
        )

        usdt_value = (
            filled_size
            * new_price
        )

        print()
        print(
            "CREATING OPPOSITE ORDER"
        )

        print(
            f"Side  : {new_side.upper()}"
        )

        print(
            f"Price : ${new_price:,.1f}"
        )

        print(
            f"Size  : {usdt_value:.2f} USDT"
        )

        try:

            response = (
                self.manager.place_limit_order(
                    side=new_side,
                    price=new_price,
                    usdt_size=usdt_value,
                )
            )

            data = response.get(
                "data",
                []
            )

            if not data:

                print(
                    "ERROR: no order returned"
                )

                return

            ord_id = data[0].get(
                "ordId",
                ""
            )

            self.orders[ord_id] = {
                "side": new_side,
                "price": new_price,
                "size": filled_size,
                "level": level,
            }

            event = (
                "SELL_REBUILD"
                if new_side == "sell"
                else "BUY_REBUILD"
            )

            log_event(
                event,
                new_side,
                level,
                str(new_price),
                str(filled_size),
                ord_id,
            )

            print(
                f"Created Order : "
                f"{ord_id}"
            )

        except Exception as e:

            print(
                "OPPOSITE ORDER ERROR:"
            )

            print(
                repr(e)
            )

    # --------------------------------------------------------
    # CHECK FILLS
    # --------------------------------------------------------

    def check_fills(self):

        open_orders = (
            self.manager.get_open_orders()
        )

        open_ids = {
            o.get("ordId")
            for o in open_orders
        }

        for ord_id in list(
            self.orders.keys()
        ):

            if ord_id in open_ids:
                continue

            try:

                details = (
                    self.manager.get_order_details(
                        ord_id
                    )
                )

                state = details.get(
                    "state"
                )

                if state != "filled":

                    continue

                side = details.get(
                    "side"
                )

                avg_price = Decimal(
                    details.get(
                        "avgPx",
                        "0"
                    ) or "0"
                )

                filled_size = Decimal(
                    details.get(
                        "accFillSz",
                        "0"
                    ) or "0"
                )

                info = self.orders[
                    ord_id
                ]

                level = info.get(
                    "level",
                    ""
                )

                print()
                print("=" * 72)
                print(
                    "🟢 ORDER FILLED"
                )
                print(
                    f"Order : {ord_id}"
                )
                print(
                    f"Side  : {side.upper()}"
                )
                print(
                    f"Level : {level}"
                )
                print(
                    f"Price : ${avg_price:,.2f}"
                )
                print(
                    f"BTC   : {filled_size}"
                )
                print("=" * 72)

                log_event(
                    "FILLED",
                    side,
                    level,
                    str(avg_price),
                    str(filled_size),
                    ord_id,
                )

                # ------------------------------------------------
                # Immediately rebuild opposite
                # ------------------------------------------------

                self.create_opposite(
                    side,
                    avg_price,
                    filled_size,
                    level,
                )

                if side == "sell":

                    self.cycles += 1

                    print(
                        f"Cycle Complete : "
                        f"{self.cycles}"
                    )

                    log_event(
                        "CYCLE_COMPLETE",
                        side,
                        level,
                        str(avg_price),
                        str(filled_size),
                        ord_id,
                    )

                del self.orders[
                    ord_id
                ]

            except Exception as e:

                print()
                print(
                    f"FILL ERROR "
                    f"{ord_id}:"
                )

                print(
                    repr(e)
                )

                # Keep state.
                # Never blindly replace an order
                # after an API error.

    # --------------------------------------------------------
    # INITIAL GRID
    # --------------------------------------------------------

    def create_initial_grid(self):

        price = get_price()

        print()
        print("=" * 72)

        print(
            f"BTC PRICE : ${price:,.2f}"
        )

        print(
            f"GRID STEP : "
            f"{GRID_PERCENT * 100:.2f}%"
        )

        print(
            f"BUY LEVELS : {BUY_LEVELS}"
        )

        print(
            f"SELL LEVELS: {SELL_LEVELS}"
        )

        print("=" * 72)

        self.create_buy_grid(
            price
        )

        self.create_sell_grid(
            price
        )

    # --------------------------------------------------------
    # RUN
    # --------------------------------------------------------

    def run(self):

        self.load_existing_orders()

        if self.orders:

            print()
            print(
                "Existing orders detected."
            )

            print(
                "NO INITIAL GRID CREATED."
            )

        else:

            self.create_initial_grid()

        print()
        print(
            "BOT RUNNING..."
        )

        while (
            self.cycles
            < MAX_CYCLES
        ):

            try:

                print()
                print(
                    f"[{now()}] "
                    f"GRID CHECK"
                )

                self.check_fills()

                print(
                    f"Active Orders : "
                    f"{len(self.orders)}"
                )

                print(
                    f"Cycles        : "
                    f"{self.cycles}"
                )

                time.sleep(
                    CHECK_INTERVAL
                )

            except KeyboardInterrupt:

                print()
                print(
                    "BOT STOPPED"
                )

                break

            except Exception as e:

                print()
                print(
                    "MAIN LOOP ERROR:"
                )

                print(
                    repr(e)
                )

                time.sleep(
                    CHECK_INTERVAL
                )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 72)
    print(
        "        ADAPTIVE GRID BOT V0.3"
    )
    print(
        "        10 x 10 SHORT GRID TEST"
    )
    print("=" * 72)

    print()
    print(
        "Exchange       : OKX DEMO"
    )

    print(
        f"Symbol         : {INST_ID}"
    )

    print(
        f"Order Size     : "
        f"{ORDER_SIZE_USDT} USDT"
    )

    print(
        f"Grid Distance  : "
        f"{GRID_PERCENT * 100:.2f}%"
    )

    print(
        f"BUY Levels     : "
        f"{BUY_LEVELS}"
    )

    print(
        f"SELL Levels    : "
        f"{SELL_LEVELS}"
    )

    print()
    print(
        "Strategy Capital : 100 USDT"
    )

    print(
        "Max Exposure     : 30 USDT"
    )

    print()
    print(
        "⚠️ DEMO TEST ONLY"
    )

    print(
        "⚠️ SPOT / NO LEVERAGE"
    )

    print()

    GridBotV03().run()


if __name__ == "__main__":
    main()