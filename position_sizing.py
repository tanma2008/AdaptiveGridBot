from decimal import Decimal


# ============================================
# Configuration
# ============================================

CAPITAL = Decimal("100")

MAX_EXPOSURE = Decimal("0.30")

GRID_COUNT = 5


# ============================================
# Trend Multipliers
# ============================================

TREND_MULTIPLIERS = {
    "UP": [
        Decimal("0.80"),
        Decimal("1.00"),
        Decimal("1.20"),
        Decimal("1.40"),
        Decimal("1.60"),
    ],

    "SIDEWAY": [
        Decimal("1.00"),
        Decimal("1.00"),
        Decimal("1.00"),
        Decimal("1.00"),
        Decimal("1.00"),
    ],

    "DOWN": [
        Decimal("1.00"),
        Decimal("0.80"),
        Decimal("0.60"),
        Decimal("0.40"),
        Decimal("0.20"),
    ],
}


# ============================================
# Calculate Base Size
# ============================================

def calculate_base_size(
    capital,
    max_exposure,
    grid_count,
):

    max_capital = (
        capital * max_exposure
    )

    return max_capital / grid_count


# ============================================
# Calculate Grid Sizes
# ============================================

def calculate_sizes(
    capital=CAPITAL,
    max_exposure=MAX_EXPOSURE,
    trend="UP",
):

    base_size = calculate_base_size(
        capital,
        max_exposure,
        GRID_COUNT,
    )

    multipliers = TREND_MULTIPLIERS[
        trend
    ]

    sizes = []

    for index, multiplier in enumerate(
        multipliers,
        start=1,
    ):

        size = (
            base_size * multiplier
        )

        sizes.append({
            "grid": index,
            "multiplier": multiplier,
            "size": size,
        })

    return sizes


# ============================================
# Main
# ============================================

def main():

    print()
    print("=" * 70)
    print("          ADAPTIVE GRID BOT")
    print("           POSITION SIZING")
    print("=" * 70)

    print()
    print(f"Capital        : {CAPITAL} USDT")
    print(
        f"Max Exposure   : "
        f"{MAX_EXPOSURE * 100:.0f}%"
    )

    max_exposure_usdt = (
        CAPITAL * MAX_EXPOSURE
    )

    print(
        f"Max Exposure $ : "
        f"{max_exposure_usdt:.2f} USDT"
    )

    print()

    for trend in [
        "UP",
        "SIDEWAY",
        "DOWN",
    ]:

        print()
        print(f"TREND = {trend}")
        print("-" * 70)

        sizes = calculate_sizes(
            trend=trend
        )

        total = Decimal("0")

        for item in sizes:

            print(
                f"Grid {item['grid']} "
                f"| Multiplier "
                f"{item['multiplier']:.2f}"
                f" | Size "
                f"{item['size']:.2f} USDT"
            )

            total += item["size"]

        print(
            f"TOTAL              "
            f"{total:.2f} USDT"
        )

    print()
    print("=" * 70)
    print("          POSITION SIZING OK")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()