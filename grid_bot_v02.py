import os
import time
import csv
from decimal import Decimal, ROUND_DOWN
from datetime import datetime

from dotenv import load_dotenv
import okx.MarketData as MarketData

from order_manager import OrderManager


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

INST_ID = "BTC-USDT"

CHECK_INTERVAL = 10

ORDER_SIZE_USDT = Decimal("5")
MAX_EXPOSURE = Decimal("30")

GRID_PERCENT = Decimal("0.001")      # 0.10%

BUY_LEVELS = 3
SELL_LEVELS = 3

MAX_CYCLES = 50

LOG_FILE = "grid_v02.csv"

FLAG = os.getenv("OKX_FLAG", "1")


# ============================================================
# MARKET API
# ============================================================

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


def log_event(
    event,
    side="",
    level="",
    price="",
    size="",
    order_id="",
    pnl="",
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
                "level",
                "price",
                "size",
                "order_id",
                "pnl",
            ])

        writer.writerow([
            now(),
            event,
            side,
            level,
            price,
            size,
            order_id,
            pnl,
        ])


def round_price(price):

    return price.quantize(
        Decimal("0.1"),
        rounding=ROUND_DOWN,
    )


# ============================================================
# GRID BOT
# ============================================================

class GridBotV02:

    def __init__(self):

        self.manager = OrderManager()

        self.orders = {}

        self.buy_positions = {}

        self.cycle_count = 0

    # --------------------------------------------------------
    # SHOW CURRENT ORDERS
    # --------------------------------------------------------

    def load_existing_orders(self):

        orders = (
            self.manager.get_open_orders()
        )

        print()
        print(
            f"Existing OKX Orders : "
            f"{len(orders)}"
        )

        for order in orders:

            ord_id = order.get(
                "ordId"
            )

            self.orders[ord_id] = {
                "side": order.get(
                    "side"
                ),
                "price": Decimal(
                    order.get(
                        "px",
                        "0"
                    )
                ),
                "size": Decimal(
                    order.get(
                        "sz",
                        "0"
                    )
                ),
            }

    # --------------------------------------------------------
    # CREATE BUY GRID
    # --------------------------------------------------------

    def create_buy_grid(
        self,
        current_price,
    ):

        print()
        print(
            "BUY GRID"
        )

        print(
            "-" * 70
        )

        for level in range(
            1,
            BUY_LEVELS + 1
        ):

            price = (
                current_price
                * (
                    Decimal("1")
                    - (
                        GRID_PERCENT
                        * level
                    )
                )
            )

            price = round_price(
                price
            )

            print(
                f"BUY {level} "
                f"| ${price:,.1f} "
                f"| {ORDER_SIZE_USDT} USDT"
            )

            try:

                response = (
                    self.manager.place_limit_order(
                        side="buy",
                        price=price,
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
                    "side": "buy",
                    "price": price,
                    "size": (
                        ORDER_SIZE_USDT
                        / price
                    ),
                    "level": level,
                }

                log_event(
                    "BUY_CREATED",
                    "buy",
                    level,
                    str(price),
                    str(
                        ORDER_SIZE_USDT
                    ),
                    ord_id,
                )

            except Exception as e:

                print(
                    f"BUY ERROR: {e}"
                )

    # --------------------------------------------------------
    # CREATE SELL GRID
    # --------------------------------------------------------

    def create_sell_grid(
        self,
        current_price,
    ):

        print()
        print(
            "SELL GRID"
        )

        print(
            "-" * 70
        )

        print(
            "NOTE: SELL orders require "
            "available BTC."
        )

        # ----------------------------------------------------
        # Get account balance
        # ----------------------------------------------------

        try:

            import okx.Account as Account

            account_api = Account.AccountAPI(
                api_key=os.getenv(
                    "OKX_API_KEY"
                ),
                api_secret_key=os.getenv(
                    "OKX_SECRET_KEY"
                ),
                passphrase=os.getenv(
                    "OKX_PASSPHRASE"
                ),
                flag=FLAG,
            )

            response = (
                account_api.get_account_balance()
            )

            if response.get("code") != "0":

                raise RuntimeError(
                    response
                )

            details = response.get(
                "data",
                []
            )

            btc_balance = Decimal(
                "0"
            )

            if details:

                for item in details[0].get(
                    "details",
                    []
                ):

                    if item.get(
                        "ccy"
                    ) == "BTC":

                        btc_balance = Decimal(
                            item.get(
                                "availBal",
                                "0"
                            )
                        )

            print(
                f"Available BTC : "
                f"{btc_balance}"
            )

        except Exception as e:

            print(
                "Could not read BTC balance:"
            )

            print(
                repr(e)
            )

            print(
                "SELL GRID SKIPPED"
            )

            return

        # ----------------------------------------------------
        # Reserve BTC for sell grid
        # ----------------------------------------------------

        btc_per_order = (
            ORDER_SIZE_USDT
            / current_price
        )

        max_sell = int(
            btc_balance
            / btc_per_order
        )

        max_sell = min(
            max_sell,
            SELL_LEVELS
        )

        if max_sell <= 0:

            print(
                "BTC inventory = 0"
            )

            print(
                "SELL GRID SKIPPED"
            )

            return

        # ----------------------------------------------------
        # Create sells
        # ----------------------------------------------------

        for level in range(
            1,
            max_sell + 1
        ):

            price = (
                current_price
                * (
                    Decimal("1")
                    + (
                        GRID_PERCENT
                        * level
                    )
                )
            )

            price = round_price(
                price
            )

            print(
                f"SELL {level} "
                f"| ${price:,.1f} "
                f"| {ORDER_SIZE_USDT} USDT"
            )

            try:

                response = (
                    self.manager.place_limit_order(
                        side="sell",
                        price=price,
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
                    "price": price,
                    "size": (
                        ORDER_SIZE_USDT
                        / price
                    ),
                    "level": level,
                }

                log_event(
                    "SELL_CREATED",
                    "sell",
                    level,
                    str(price),
                    str(
                        ORDER_SIZE_USDT
                    ),
                    ord_id,
                )

            except Exception as e:

                print(
                    f"SELL ERROR: {e}"
                )

    # --------------------------------------------------------
    # CHECK FILLS
    # --------------------------------------------------------

    def check_fills(self):

        open_orders = (
            self.manager.get_open_orders()
        )

        open_ids = {
            order.get(
                "ordId"
            )
            for order in open_orders
        }

        # ----------------------------------------------------
        # Check known orders
        # ----------------------------------------------------

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

                info = self.orders[
                    ord_id
                ]

                level = info.get(
                    "level",
                    ""
                )

                print()
                print(
                    "=" * 70
                )

                print(
                    "🟢 ORDER FILLED"
                )

                print(
                    f"Side  : {side}"
                )

                print(
                    f"Level : {level}"
                )

                print(
                    f"Price : {avg_px}"
                )

                print(
                    f"BTC   : {filled}"
                )

                print(
                    "=" * 70
                )

                log_event(
                    "FILLED",
                    side,
                    level,
                    str(avg_px),
                    str(filled),
                    ord_id,
                )

                # ------------------------------------------------
                # BUY FILLED → SELL ABOVE
                # ------------------------------------------------

                if side == "buy":

                    sell_price = (
                        avg_px
                        * (
                            Decimal("1")
                            + GRID_PERCENT
                        )
                    )

                    sell_price = round_price(
                        sell_price
                    )

                    sell_usdt = (
                        filled
                        * sell_price
                    )

                    response = (
                        self.manager.place_limit_order(
                            side="sell",
                            price=sell_price,
                            usdt_size=sell_usdt,
                        )
                    )

                    data = response.get(
                        "data",
                        []
                    )

                    if data:

                        new_id = data[0].get(
                            "ordId",
                            ""
                        )

                        self.orders[
                            new_id
                        ] = {
                            "side": "sell",
                            "price": sell_price,
                            "size": filled,
                            "level": level,
                            "from_buy": ord_id,
                        }

                        print(
                            f"SELL CREATED "
                            f"@ {sell_price}"
                        )

                        log_event(
                            "SELL_CREATED_FROM_BUY",
                            "sell",
                            level,
                            str(sell_price),
                            str(filled),
                            new_id,
                        )

                # ------------------------------------------------
                # SELL FILLED
                # ------------------------------------------------

                elif side == "sell":

                    print(
                        "SELL FILLED"
                    )

                    self.cycle_count += 1

                    print(
                        f"Cycle : "
                        f"{self.cycle_count}"
                    )

                    log_event(
                        "CYCLE_COMPLETE",
                        "sell",
                        level,
                        str(avg_px),
                        str(filled),
                        ord_id,
                    )

                del self.orders[
                    ord_id
                ]

            except Exception as e:

                print()
                print(
                    f"Fill check error "
                    f"{ord_id}:"
                )

                print(
                    repr(e)
                )

                # IMPORTANT:
                # Do not delete order.
                # Do not create replacement order.
                continue

    # --------------------------------------------------------
    # START GRID
    # --------------------------------------------------------

    def start_grid(self):

        current_price = get_price()

        print()
        print(
            "=" * 72
        )

        print(
            f"BTC PRICE : "
            f"${current_price:,.2f}"
        )

        print(
            f"Grid step : "
            f"{GRID_PERCENT * 100:.2f}%"
        )

        print(
            "=" * 72
        )

        self.create_buy_grid(
            current_price
        )

        self.create_sell_grid(
            current_price
        )

    # --------------------------------------------------------
    # RUN
    # --------------------------------------------------------

    def run(self):

        self.load_existing_orders()

        # ----------------------------------------------------
        # Safety
        # ----------------------------------------------------

        if self.orders:

            print()
            print(
                "Existing orders detected."
            )

            print(
                "Bot will NOT create "
                "a new initial grid."
            )

        else:

            self.start_grid()

        # ----------------------------------------------------
        # Main loop
        # ----------------------------------------------------

        while (
            self.cycle_count
            < MAX_CYCLES
        ):

            try:

                print()
                print(
                    f"[{now()}] "
                    f"Checking grid..."
                )

                self.check_fills()

                print(
                    f"Active Orders : "
                    f"{len(self.orders)}"
                )

                print(
                    f"Cycles        : "
                    f"{self.cycle_count}"
                )

                time.sleep(
                    CHECK_INTERVAL
                )

            except KeyboardInterrupt:

                print()
                print(
                    "Bot stopped."
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
        "        ADAPTIVE GRID BOT V0.2"
    )
    print(
        "        TWO-SIDED GRID TEST"
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
        "⚠️ TEST VERSION"
    )

    print(
        "⚠️ OKX DEMO ONLY"
    )

    print()

    bot = GridBotV02()

    bot.run()


if __name__ == "__main__":

    main()