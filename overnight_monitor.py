import time
from datetime import datetime

from order_manager import OrderManager


CHECK_INTERVAL = 30

TARGET_ORDER_ID = "3860621550732709888"

LOG_FILE = "overnight_log.txt"


def log(message):

    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    line = f"[{now}] {message}"

    print(line)

    with open(
        LOG_FILE,
        "a",
        encoding="utf-8",
    ) as f:

        f.write(line + "\n")


def main():

    print()
    print("=" * 72)
    print("       ADAPTIVE GRID BOT - OVERNIGHT DEMO")
    print("=" * 72)

    print()
    print("Mode        : MONITOR ONLY")
    print("New Orders  : DISABLED")
    print("SELL        : DISABLED")
    print(
        f"Order ID    : {TARGET_ORDER_ID}"
    )
    print(
        f"Interval    : {CHECK_INTERVAL} sec"
    )
    print(
        f"Log         : {LOG_FILE}"
    )

    manager = OrderManager()

    previous_state = None

    while True:

        try:

            order = manager.get_order_details(
                TARGET_ORDER_ID
            )

            state = order.get(
                "state",
                ""
            )

            filled = order.get(
                "accFillSz",
                "0"
            )

            avg_px = order.get(
                "avgPx",
                ""
            )

            fee = order.get(
                "fee",
                "0"
            )

            # ----------------------------------------------
            # State change
            # ----------------------------------------------

            if state != previous_state:

                log(
                    f"ORDER STATE: "
                    f"{previous_state} -> {state}"
                )

                log(
                    f"Filled={filled} "
                    f"AvgPx={avg_px} "
                    f"Fee={fee}"
                )

                previous_state = state

            else:

                log(
                    f"STATE={state} "
                    f"Filled={filled}"
                )

            # ----------------------------------------------
            # Filled
            # ----------------------------------------------

            if state == "filled":

                log(
                    "🟢 BUY FILLED"
                )

                log(
                    f"BTC={filled}"
                )

                log(
                    f"Average Price={avg_px}"
                )

                log(
                    "SELL IS DISABLED."
                )

                log(
                    "MONITOR WILL CONTINUE."
                )

            # ----------------------------------------------
            # Cancelled
            # ----------------------------------------------

            if state == "canceled":

                log(
                    "🟡 ORDER CANCELLED"
                )

                break

        except KeyboardInterrupt:

            log(
                "Monitor stopped manually."
            )

            break

        except Exception as e:

            log(
                f"ERROR: {repr(e)}"
            )

        time.sleep(
            CHECK_INTERVAL
        )


if __name__ == "__main__":

    main()