from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

DEMO_ONLY = True
ALLOW_ORDER_SUBMISSION = False

@dataclass
class OrderIntent:
    side: str
    price: Decimal
    quantity: Decimal
    grid_level: int
    client_order_id: str

class OrderManager:
    def __init__(self):
        self.orders = {}

    def validate_intent(self, intent: OrderIntent) -> None:
        if intent.side not in {"BUY", "SELL"}: raise ValueError("Invalid order side")
        if intent.price <= 0: raise ValueError("Order price must be positive")
        if intent.quantity <= 0: raise ValueError("Order quantity must be positive")
        if not intent.client_order_id: raise ValueError("client_order_id is required")
        if intent.client_order_id in self.orders: raise ValueError("Duplicate client_order_id")

    def register_intent(self, intent: OrderIntent) -> None:
        self.validate_intent(intent)
        self.orders[intent.client_order_id] = intent

    def submit(self, intent: OrderIntent):
        self.validate_intent(intent)
        if not DEMO_ONLY or not ALLOW_ORDER_SUBMISSION:
            raise RuntimeError("ORDER BLOCKED: DEMO_ONLY/ALLOW_ORDER_SUBMISSION safety gate")
        raise NotImplementedError("Exchange adapter not connected")

    def cancel(self, client_order_id: str):
        if client_order_id not in self.orders: raise KeyError("Unknown client_order_id")
        if not DEMO_ONLY or not ALLOW_ORDER_SUBMISSION:
            raise RuntimeError("CANCEL BLOCKED: DEMO_ONLY/ALLOW_ORDER_SUBMISSION safety gate")
        raise NotImplementedError("Exchange adapter not connected")

    def status(self, client_order_id: str) -> Optional[OrderIntent]:
        return self.orders.get(client_order_id)

def self_test():
    manager = OrderManager()
    intent = OrderIntent("BUY", Decimal("2500"), Decimal("0.025"), -1, "ETHV48-BUY-001")
    try:
        manager.submit(intent)
    except RuntimeError as exc:
        assert "ORDER BLOCKED" in str(exc)
    else: raise AssertionError("Order submission safety gate failed")
    manager.register_intent(intent)
    assert manager.status("ETHV48-BUY-001") == intent
    try:
        manager.register_intent(intent)
    except ValueError: pass
    else: raise AssertionError("Duplicate order ID was not blocked")
    try:
        manager.cancel("ETHV48-BUY-001")
    except RuntimeError as exc:
        assert "CANCEL BLOCKED" in str(exc)
    else: raise AssertionError("Cancel safety gate failed")
    print("ORDER MANAGER SELF-TEST: PASS")
    print("Order submission : BLOCKED")
    print("Cancel           : BLOCKED")
    print("Duplicate ID     : BLOCKED")
    print("Exchange writes  : NONE")

if __name__ == "__main__": self_test()
