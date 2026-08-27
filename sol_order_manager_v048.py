import os
from decimal import Decimal, ROUND_DOWN
import os

from dotenv import load_dotenv

import okx.Trade as Trade


# ============================================================
# SETTINGS
# ============================================================

load_dotenv()

API_KEY = os.getenv("OKX_API_KEY")
SECRET_KEY = os.getenv("OKX_SECRET_KEY")
PASSPHRASE = os.getenv("OKX_PASSPHRASE")
FLAG = os.getenv("OKX_FLAG", "1")

INST_ID = "SOL-USDT"


# ============================================================
# VALIDATION
# ============================================================

if not API_KEY:
    raise RuntimeError("OKX_API_KEY is missing")

if not SECRET_KEY:
    raise RuntimeError("OKX_SECRET_KEY is missing")

if not PASSPHRASE:
    raise RuntimeError("OKX_PASSPHRASE is missing")


# ============================================================
# OKX TRADE API
# ============================================================

trade_api = Trade.TradeAPI(
    api_key=API_KEY,
    api_secret_key=SECRET_KEY,
    passphrase=PASSPHRASE,
    flag=FLAG,
)


# ============================================================
# ORDER MANAGER
# ============================================================

class OrderManager:

    def __init__(self):

        self.inst_id = INST_ID

    # --------------------------------------------------------
    # GET OPEN ORDERS
    # --------------------------------------------------------

    def get_open_orders(self):

        response = trade_api.get_order_list(
            instId=self.inst_id
        )

        if response.get("code") != "0":

            raise RuntimeError(
                f"OKX Open Orders Error: {response}"
            )

        return response.get(
            "data",
            []
        )

    # --------------------------------------------------------
    # GET ORDER DETAILS
    # --------------------------------------------------------

    def get_order_details(
        self,
        ord_id,
    ):

        response = trade_api.get_order(
            instId=self.inst_id,
            ordId=str(ord_id),
        )

        if response.get("code") != "0":

            raise RuntimeError(
                f"OKX Order Error: {response}"
            )

        data = response.get(
            "data",
            []
        )

        if not data:

            raise RuntimeError(
                f"Order not found: {ord_id}"
            )

        return data[0]

    # --------------------------------------------------------
    # CANCEL ORDER
    # --------------------------------------------------------

    def cancel_order(
        self,
        ord_id,
    ):

        response = trade_api.cancel_order(
            instId=self.inst_id,
            ordId=str(ord_id),
        )

        if response.get("code") != "0":

            raise RuntimeError(
                f"OKX Cancel Error: {response}"
            )

        return response

    # --------------------------------------------------------
    # CALCULATE SOL SIZE
    # --------------------------------------------------------

    def sol_size_from_usdt(
        self,
        usdt_size,
        price,
    ):

        usdt_size = Decimal(
            str(usdt_size)
        )

        price = Decimal(
            str(price)
        )

        if price <= 0:

            raise ValueError(
                "Price must be greater than zero"
            )

        sol_size = (
            usdt_size / price
        )

        # SOL-USDT minimum precision
        sol_size = sol_size.quantize(
            Decimal("0.000001"),
            rounding=ROUND_DOWN,
        )

        return sol_size

    # --------------------------------------------------------
    # PLACE LIMIT ORDER
    # --------------------------------------------------------

    def place_limit_order(
        self,
        side,
        price,
        usdt_size,
    ):

        side = str(
            side
        ).lower()

        if side not in (
            "buy",
            "sell",
        ):

            raise ValueError(
                "Side must be buy or sell"
            )

        price = Decimal(
            str(price)
        )

        usdt_size = Decimal(
            str(usdt_size)
        )

        if price <= 0:

            raise ValueError(
                "Price must be greater than zero"
            )

        if usdt_size <= 0:

            raise ValueError(
                "USDT size must be greater than zero"
            )

        sol_size = (
            self.sol_size_from_usdt(
                usdt_size,
                price,
            )
        )

        if sol_size <= 0:

            raise ValueError(
                "Calculated SOL size is zero"
            )

        # ----------------------------------------------------
        # IMPORTANT
        #
        # Do NOT use:
        #
        #     trade_api.place_order()
        #
        # The installed OKX SDK injects:
        #
        #     stpMode = ""
        #
        # which causes:
        #
        #     51000 Parameter stpMode error
        #
        # Use the authenticated request method directly
        # with only the required parameters.
        # ----------------------------------------------------

        params = {
            "instId": self.inst_id,
            "tdMode": "cash",
            "side": side,
            "ordType": "limit",
            "px": str(price),
            "sz": str(sol_size),
        }

        try:

            response = (
                trade_api._request_with_params(
                    Trade.POST,
                    Trade.PLACR_ORDER,
                    params,
                )
            )

        except Exception as exc:

            raise RuntimeError(
                f"OKX Place Order Exception: "
                f"{type(exc).__name__}: {exc}"
            )

        if response.get("code") != "0":

            raise RuntimeError(
                f"OKX Place Order Error: {response}"
            )

        return response


# ============================================================
# TEST
# ============================================================

def main():

    print()
    print("=" * 70)
    print("        ADAPTIVE GRID BOT")
    print("             ORDER MANAGER")
    print("=" * 70)

    print()

    print(
        f"Exchange : "
        f"{'OKX DEMO' if FLAG == '1' else 'OKX LIVE'}"
    )

    print(
        f"Symbol   : {INST_ID}"
    )

    print()

    print(
        "Checking open orders..."
    )

    print(
        "-" * 70
    )

    manager = OrderManager()

    orders = (
        manager.get_open_orders()
    )

    print(
        f"Open Orders : {len(orders)}"
    )

    if orders:

        print()

        for order in orders:

            print(
                f"Order ID : "
                f"{order.get('ordId', '')}"
            )

            print(
                f"State    : "
                f"{order.get('state', '')}"
            )

            print(
                f"Side     : "
                f"{order.get('side', '')}"
            )

            print(
                f"Price    : "
                f"{order.get('px', '')}"
            )

            print(
                f"Size     : "
                f"{order.get('sz', '')}"
            )

            print(
                f"Filled   : "
                f"{order.get('accFillSz', '')}"
            )

            print()

    print("=" * 70)
    print(
        "       ORDER MANAGER OK"
    )
    print("=" * 70)


if __name__ == "__main__":

    main()