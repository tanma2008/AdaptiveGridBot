import time
from decimal import Decimal

from order_manager import OrderManager


CHECK_INTERVAL = 10


def print_order(order):

    print("-" * 72)

    print(
        f"Order ID : {order.get('ordId', '-')}"
    )

    print(
        f"State    : {order.get('state', '-')}"
    )

    print(
        f"Side     : {order.get('side', '-')}"
    )

    print(
        f"Price    : {order.get('px', '-')}"
    )

    print(
        f"Size     : {order.get('sz', '-')}"
    )

    print(
        f"Filled   : {order.get('accFillSz', '-')}"
    )

    print(
        f"Avg Fill : {order.get('avgPx', '-')}"
    )

    print(
        f"Fee      : {order.get('fee', '-')}"
    )


def main():

    print()
    print("=" * 72)
    print("          ADAPTIVE GRID BOT")
    print("             ORDER MONITOR")
    print("=" * 72)

    manager = OrderManager()

    print()
    print(
        f"Checking every {CHECK_INTERVAL} seconds"
    )

    print(
        "Mode : READ / MONITOR ONLY"
    )

    print()

    while True:

        try:

            orders = manager.get_open_orders()

            print()
            print(
                "=" * 72
            )

            print(
                f"OPEN ORDERS : {len(orders)}"
            )

            if not orders:

                print(
                    "No open orders."
                )

                print(
                    "The first Demo order may "
                    "have been filled or cancelled."
                )

            else:

                for order in orders:

                    print_order(order)

            print(
                "=" * 72
            )

        except KeyboardInterrupt:

            print()
            print(
                "Monitor stopped."
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

        print()
        print(
            f"Next check in "
            f"{CHECK_INTERVAL} seconds..."
        )

        time.sleep(
            CHECK_INTERVAL
        )


if __name__ == "__main__":

    main()