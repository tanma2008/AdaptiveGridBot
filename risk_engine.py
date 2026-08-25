from decimal import Decimal


# ============================================
# Risk Configuration
# ============================================

CAPITAL = Decimal("100")

MAX_EXPOSURE = Decimal("0.30")

MAX_DRAWDOWN = Decimal("0.10")

MIN_ORDER_SIZE = Decimal("1.00")


# ============================================
# Exposure
# ============================================

def max_exposure_amount(
    capital,
    max_exposure,
):

    return capital * max_exposure


# ============================================
# Scale Orders
# ============================================

def scale_orders(
    orders,
    allowed_exposure,
):

    total_requested = sum(
        item["size"]
        for item in orders
    )

    if total_requested <= allowed_exposure:

        return orders

    scale_factor = (
        allowed_exposure
        / total_requested
    )

    scaled = []

    for item in orders:

        new_size = (
            item["size"]
            * scale_factor
        )

        scaled.append({
            **item,
            "original_size": item["size"],
            "size": new_size,
        })

    return scaled


# ============================================
# Risk Check
# ============================================

def risk_check(
    capital,
    current_exposure,
    requested_exposure,
    max_exposure=MAX_EXPOSURE,
):

    allowed = (
        capital * max_exposure
    )

    remaining = (
        allowed - current_exposure
    )

    if remaining <= 0:

        return {
            "allowed": False,
            "reason": "MAX_EXPOSURE_REACHED",
            "remaining": Decimal("0"),
        }

    if requested_exposure <= remaining:

        return {
            "allowed": True,
            "reason": "PASS",
            "remaining": remaining,
        }

    return {
        "allowed": False,
        "reason": "EXPOSURE_LIMIT",
        "remaining": remaining,
    }


# ============================================
# Main
# ============================================

def main():

    print()
    print("=" * 70)
    print("             ADAPTIVE GRID BOT")
    print("                RISK ENGINE")
    print("=" * 70)

    allowed = max_exposure_amount(
        CAPITAL,
        MAX_EXPOSURE,
    )

    print()
    print(
        f"Capital          : "
        f"{CAPITAL:.2f} USDT"
    )

    print(
        f"Max Exposure     : "
        f"{allowed:.2f} USDT"
    )

    # ----------------------------------------
    # Example: no current position
    # ----------------------------------------

    current_exposure = Decimal("0")

    requested_exposure = Decimal("36")

    result = risk_check(
        capital=CAPITAL,
        current_exposure=current_exposure,
        requested_exposure=requested_exposure,
    )

    print()
    print("RISK CHECK")
    print("-" * 70)

    print(
        f"Current Exposure : "
        f"{current_exposure:.2f}"
    )

    print(
        f"Requested        : "
        f"{requested_exposure:.2f}"
    )

    print(
        f"Allowed          : "
        f"{allowed:.2f}"
    )

    print(
        f"Result           : "
        f"{result['reason']}"
    )

    # ----------------------------------------
    # Scale example
    # ----------------------------------------

    orders = [
        {
            "grid": 1,
            "size": Decimal("4.80"),
        },
        {
            "grid": 2,
            "size": Decimal("6.00"),
        },
        {
            "grid": 3,
            "size": Decimal("7.20"),
        },
        {
            "grid": 4,
            "size": Decimal("8.40"),
        },
        {
            "grid": 5,
            "size": Decimal("9.60"),
        },
    ]

    scaled = scale_orders(
        orders,
        allowed,
    )

    print()
    print("SCALED ORDERS")
    print("-" * 70)

    total = Decimal("0")

    for item in scaled:

        print(
            f"Grid {item['grid']} "
            f"| Original "
            f"{item['original_size']:.2f}"
            f" | Approved "
            f"{item['size']:.2f}"
        )

        total += item["size"]

    print()
    print(
        f"Approved Total : "
        f"{total:.2f} USDT"
    )

    print()
    print("=" * 70)
    print("               RISK ENGINE OK")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()