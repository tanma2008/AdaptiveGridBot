import time
from decimal import Decimal

from order_manager import OrderManager


CHECK_INTERVAL = 10


def show_order(order):

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
        f"Order BTC: {order.get('sz', '-')}"
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
    print("             FILL MANAGER")
    print("=" * 72)

    print()
    print("Mode : MONITOR ONLY")
    print("SELL : DISABLED")
    print(
        f"Interval : {CHECK_INTERVAL} seconds"
    )

    manager = OrderManager()

    last_state = {}

    while True:

        try:

            orders = manager.get_open_orders()

            print()
            print("=" * 72)
            print(
                f"OPEN ORDERS : {len(orders)}"
            )

            # ------------------------------------------------
            # Currently open orders
            # ------------------------------------------------

            current_ids = set()

            for order in orders:

                ord_id = order.get(
                    "ordId"
                )

                current_ids.add(
                    ord_id
                )

                show_order(order)

                last_state[ord_id] = (
                    order.get("state")
                )

            # ------------------------------------------------
            # Detect orders that disappeared
            # ------------------------------------------------

            disappeared = [
                ord_id
                for ord_id in last_state
                if ord_id not in current_ids
            ]

            for ord_id in disappeared:

                print()
                print(
                    "ORDER NO LONGER OPEN"
                )

                print(
                    f"Order ID : {ord_id}"
                )

                print(
                    "Checking final order state..."
                )

                try:

                    details = (
                        manager.get_order_details(
                            ord_id
                        )
                    )

                    print()
                    print(
                        "FINAL ORDER STATE"
                    )

                    show_order(
                        details
                    )

                    state = details.get(
                        "state"
                    )

                    if state == "filled":

                        filled = Decimal(
                            details.get(
                                "accFillSz",
                                "0"
                            )
                        )

                        avg_price = Decimal(
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
                            "🟢 ORDER FILLED"
                        )

                        print(
                            f"BTC Filled : "
                            f"{filled}"
                        )

                        print(
                            f"Avg Price  : "
                            f"${avg_price:,.2f}"
                        )

                        print(
                            "SELL ORDER : DISABLED"
                        )

                        print(
                            "=" * 72
                        )

                    elif state == "canceled":

                        print()
                        print(
                            "🟡 ORDER CANCELLED"
                        )

                    else:

                        print()
                        print(
                            f"Order state : {state}"
                        )

                except Exception as e:

                    print()
                    print(
                        "Could not retrieve "
                        "final order state:"
                    )

                    print(
                        repr(e)
                    )

                del last_state[ord_id]

            print()
            print("=" * 72)

        except KeyboardInterrupt:

            print()
            print(
                "Fill Manager stopped."
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