import os
from decimal import Decimal, ROUND_DOWN

from dotenv import load_dotenv

import okx.Account as Account
import okx.MarketData as MarketData
import okx.Trade as Trade


# ============================================================
# ETH/USDT ORDER MANAGER v4.9
# DEMO ONLY
# ============================================================

load_dotenv(".env.v49", override=True)

INST_ID = "ETH-USDT"
FLAG = os.getenv("OKX_FLAG", "1")

API_KEY = os.getenv("OKX_API_KEY")
SECRET_KEY = os.getenv("OKX_SECRET_KEY")
PASSPHRASE = os.getenv("OKX_PASSPHRASE")

if not API_KEY:
    raise RuntimeError("OKX_API_KEY is missing")
if not SECRET_KEY:
    raise RuntimeError("OKX_SECRET_KEY is missing")
if not PASSPHRASE:
    raise RuntimeError("OKX_PASSPHRASE is missing")
if FLAG != "1":
    raise RuntimeError(
        "SAFETY STOP: ETH v4.9 requires OKX_FLAG=1 (DEMO)."
    )


trade_api = Trade.TradeAPI(
    api_key=API_KEY,
    api_secret_key=SECRET_KEY,
    passphrase=PASSPHRASE,
    flag="1",
    debug=False,
)

account_api = Account.AccountAPI(
    api_key=API_KEY,
    api_secret_key=SECRET_KEY,
    passphrase=PASSPHRASE,
    flag="1",
    debug=False,
)

market_api = MarketData.MarketAPI()


class OrderManager:
    """OKX spot ETH/USDT adapter for the v4.9 demo loop."""

    def __init__(self):
        self.inst_id = INST_ID
        self.tick_size, self.lot_size, self.min_size = self._instrument_rules()

    def _instrument_rules(self):
        # This installed OKX SDK exposes SPOT instruments through
        # AccountAPI.get_instruments(), matching the existing ETH v4.8 code.
        response = account_api.get_instruments(instType="SPOT")
        if response.get("code") != "0":
            raise RuntimeError(f"OKX Instrument Error: {response}")
        item = next(
            (x for x in response.get("data", []) if x.get("instId") == self.inst_id),
            None,
        )
        if not item:
            raise RuntimeError(f"Instrument not found: {self.inst_id}")
        tick_size = Decimal(item.get("tickSz", "0.01"))
        lot_size = Decimal(item.get("lotSz", "0.0001"))
        min_size = Decimal(item.get("minSz", str(lot_size)))
        return tick_size, lot_size, min_size

    @staticmethod
    def _round_down(value, quantum):
        value = Decimal(str(value))
        quantum = Decimal(str(quantum))
        return (value / quantum).to_integral_value(rounding=ROUND_DOWN) * quantum

    def normalize_price(self, price):
        price = self._round_down(price, self.tick_size)
        if price <= 0:
            raise ValueError("Normalized price must be positive")
        return price

    def eth_size_from_usdt(self, usdt_size, price):
        usdt_size = Decimal(str(usdt_size))
        price = Decimal(str(price))
        if usdt_size <= 0:
            raise ValueError("USDT size must be greater than zero")
        if price <= 0:
            raise ValueError("Price must be greater than zero")

        eth_size = self._round_down(usdt_size / price, self.lot_size)
        if eth_size < self.min_size:
            raise ValueError(
                f"Calculated ETH size {eth_size} is below OKX min size {self.min_size}"
            )
        return eth_size

    def get_open_orders(self):
        response = trade_api.get_order_list(instId=self.inst_id)
        if response.get("code") != "0":
            raise RuntimeError(f"OKX Open Orders Error: {response}")
        return response.get("data", [])

    def get_order_details(self, ord_id):
        response = trade_api.get_order(
            instId=self.inst_id,
            ordId=str(ord_id),
        )
        if response.get("code") != "0":
            raise RuntimeError(f"OKX Order Error: {response}")
        data = response.get("data", [])
        if not data:
            raise RuntimeError(f"Order not found: {ord_id}")
        return data[0]

    def cancel_order(self, ord_id):
        response = trade_api.cancel_order(
            instId=self.inst_id,
            ordId=str(ord_id),
        )
        if response.get("code") != "0":
            raise RuntimeError(f"OKX Cancel Error: {response}")
        return response

    def get_balances(self):
        response = account_api.get_account_balance()
        if response.get("code") != "0":
            raise RuntimeError(f"OKX Account Error: {response}")

        details = response.get("data", [{}])[0].get("details", [])
        balances = {}
        for item in details:
            ccy = item.get("ccy")
            if ccy:
                balances[ccy] = Decimal(item.get("availBal", "0"))
        return balances

    def place_limit_order(self, side, price, usdt_size):
        side = str(side).lower()
        if side not in {"buy", "sell"}:
            raise ValueError("Side must be buy or sell")

        price = self.normalize_price(price)
        eth_size = self.eth_size_from_usdt(usdt_size, price)

        params = {
            "instId": self.inst_id,
            "tdMode": "cash",
            "side": side,
            "ordType": "limit",
            "px": str(price),
            "sz": str(eth_size),
        }

        try:
            # Use the same direct authenticated request path proven by BTC v4.9.
            response = trade_api._request_with_params(
                Trade.POST,
                Trade.PLACR_ORDER,
                params,
            )
        except Exception as exc:
            raise RuntimeError(
                f"OKX Place Order Exception: {type(exc).__name__}: {exc}"
            )

        if response.get("code") != "0":
            raise RuntimeError(f"OKX Place Order Error: {response}")
        return response


def self_test():
    manager = OrderManager()
    assert manager.inst_id == "ETH-USDT"
    assert manager.tick_size > 0
    assert manager.lot_size > 0
    assert manager.min_size > 0

    price = manager.normalize_price("2500.12345")
    size = manager.eth_size_from_usdt("5.00", price)
    assert price > 0
    assert size >= manager.min_size

    print("ETH ORDER MANAGER v4.9 SELF-TEST: PASS")
    print(f"Symbol       : {manager.inst_id}")
    print(f"Tick size    : {manager.tick_size}")
    print(f"Lot size     : {manager.lot_size}")
    print(f"Min size     : {manager.min_size}")
    print(f"Demo flag    : {FLAG}")
    print("Order write  : NOT EXECUTED BY SELF-TEST")


if __name__ == "__main__":
    self_test()
