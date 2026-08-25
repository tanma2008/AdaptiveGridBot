cat > okx_demo_report_v01.py <<'PY'
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from dotenv import load_dotenv
import okx.Trade as Trade


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

API_KEY = os.getenv("OKX_API_KEY")
SECRET_KEY = os.getenv("OKX_SECRET_KEY")
PASSPHRASE = os.getenv("OKX_PASSPHRASE")
FLAG = os.getenv("OKX_FLAG", "1")

INST_TYPE = "SPOT"
INST_ID = "BTC-USDT"
LIMIT = "100"


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
# API
# ============================================================

api = Trade.TradeAPI(
    api_key=API_KEY,
    api_secret_key=SECRET_KEY,
    passphrase=PASSPHRASE,
    flag=FLAG,
)


# ============================================================
# HELPERS
# ============================================================

def d(value):
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def ms(dt):
    return str(int(dt.timestamp() * 1000))


def fmt_usdt(value):
    return f"{value:.6f}"


def fmt_btc(value):
    return f"{value:.8f}"


# ============================================================
# FETCH FILLS
# ============================================================

def get_fills_24h():

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)

    after = ms(start)
    before = ms(now)

    all_rows = []

    cursor = ""

    while True:

        response = api.get_fills_history(
            instType=INST_TYPE,
            instId=INST_ID,
            after=after,
            before=before,
            limit=LIMIT,
        )

        if response.get("code") != "0":
            raise RuntimeError(
                f"OKX Fill History Error: {response}"
            )

        rows = response.get("data", [])

        if not rows:
            break

        all_rows.extend(rows)

        if len(rows) < int(LIMIT):
            break

        # Move the upper boundary backward using the oldest fill.
        oldest = min(
            int(row.get("ts", "0"))
            for row in rows
            if row.get("ts")
        )

        if oldest <= int(after):
            break

        before = str(oldest - 1)

    # Deduplicate by tradeId when available.
    unique = {}

    for row in all_rows:

        key = (
            row.get("tradeId")
            or row.get("fillId")
            or (
                row.get("ordId"),
                row.get("ts"),
                row.get("side"),
                row.get("fillSz"),
                row.get("fillPx"),
            )
        )

        unique[key] = row

    rows = list(unique.values())

    rows.sort(
        key=lambda x: int(x.get("ts", "0"))
    )

    return rows, start, now


# ============================================================
# ANALYSIS
# ============================================================

def analyze(rows):

    buy_count = 0
    sell_count = 0

    buy_btc = Decimal("0")
    sell_btc = Decimal("0")

    buy_value = Decimal("0")
    sell_value = Decimal("0")

    fees_usdt = Decimal("0")

    fee_currency = {}

    for row in rows:

        side = str(
            row.get("side", "")
        ).lower()

        px = d(row.get("fillPx", "0"))
        sz = d(row.get("fillSz", "0"))

        value = px * sz

        if side == "buy":

            buy_count += 1
            buy_btc += sz
            buy_value += value

        elif side == "sell":

            sell_count += 1
            sell_btc += sz
            sell_value += value

        fee = d(row.get("fee", "0"))
        fee_ccy = row.get("feeCcy", "")

        fee_currency[fee_ccy] = (
            fee_currency.get(
                fee_ccy,
                Decimal("0")
            ) + fee
        )

        # Convert USDT-denominated fee directly.
        if fee_ccy == "USDT":
            fees_usdt += abs(fee)

    # Simple cash-flow view.
    gross_cash_flow = (
        sell_value
        - buy_value
    )

    net_cash_flow = (
        gross_cash_flow
        - fees_usdt
    )

    return {
        "buy_count": buy_count,
        "sell_count": sell_count,
        "buy_btc": buy_btc,
        "sell_btc": sell_btc,
        "buy_value": buy_value,
        "sell_value": sell_value,
        "gross_cash_flow": gross_cash_flow,
        "fees_usdt": fees_usdt,
        "net_cash_flow": net_cash_flow,
        "fee_currency": fee_currency,
    }


# ============================================================
# PRINT
# ============================================================

def main():

    print()
    print("=" * 76)
    print("          OKX DEMO v4.8 — LAST 24 HOURS REPORT")
    print("=" * 76)

    print()
    print(f"Mode       : {'OKX DEMO' if FLAG == '1' else 'OKX LIVE'}")
    print(f"Symbol     : {INST_ID}")
    print(f"Instrument : {INST_TYPE}")

    rows, start, now = get_fills_24h()

    result = analyze(rows)

    print()
    print("=" * 76)
    print("PERIOD")
    print("=" * 76)

    print(f"From       : {start}")
    print(f"To         : {now}")
    print(f"Fills      : {len(rows)}")

    print()
    print("=" * 76)
    print("TRADING ACTIVITY")
    print("=" * 76)

    print(f"BUY fills          : {result['buy_count']}")
    print(f"SELL fills         : {result['sell_count']}")

    print(
        f"Bought BTC         : "
        f"{fmt_btc(result['buy_btc'])}"
    )

    print(
        f"Sold BTC           : "
        f"{fmt_btc(result['sell_btc'])}"
    )

    print(
        f"BUY value          : "
        f"{fmt_usdt(result['buy_value'])} USDT"
    )

    print(
        f"SELL value         : "
        f"{fmt_usdt(result['sell_value'])} USDT"
    )

    print()
    print("=" * 76)
    print("CASH-FLOW VIEW")
    print("=" * 76)

    print(
        f"Gross SELL-BUY     : "
        f"{fmt_usdt(result['gross_cash_flow'])} USDT"
    )

    print(
        f"USDT fees          : "
        f"{fmt_usdt(result['fees_usdt'])} USDT"
    )

    print(
        f"Net cash flow      : "
        f"{fmt_usdt(result['net_cash_flow'])} USDT"
    )

    print()
    print("Fee currencies:")

    for ccy, value in result["fee_currency"].items():
        print(
            f"  {ccy or '(unknown)'} : "
            f"{value}"
        )

    print()
    print("=" * 76)
    print("IMPORTANT")
    print("=" * 76)
    print(
        "Net cash flow above is NOT yet realized Grid P/L."
    )
    print(
        "It is SELL value - BUY value - USDT fees."
    )
    print(
        "Because the Demo account already had BTC,"
    )
    print(
        "inventory-based P/L must be reconciled separately."
    )

    print()
    print("=" * 76)
    print("OKX DEMO REPORT COMPLETE")
    print("=" * 76)


if __name__ == "__main__":
    main()
PY