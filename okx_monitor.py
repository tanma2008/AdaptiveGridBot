import os
from decimal import Decimal
from dotenv import load_dotenv
from okx import Account
import okx.MarketData as MarketData

load_dotenv()

API_KEY = os.getenv("OKX_API_KEY")
API_SECRET = os.getenv("OKX_API_SECRET")
PASSPHRASE = os.getenv("OKX_PASSPHRASE")
FLAG = os.getenv("OKX_FLAG", "1")

if not all([API_KEY, API_SECRET, PASSPHRASE]):
    raise RuntimeError("Missing OKX API credentials in .env")

# =========================
# OKX API
# =========================

account = Account.AccountAPI(
    api_key=API_KEY,
    api_secret_key=API_SECRET,
    passphrase=PASSPHRASE,
    flag=FLAG,
    debug=False,
)
market = MarketData.MarketAPI(
    flag=FLAG,
    debug=False,
)

# =========================
# Account
# =========================

def get_account():
    response = account.get_account_balance()

    if response.get("code") != "0":
        raise RuntimeError(f"OKX Account Error: {response}")

    return response["data"][0]


def get_balance(data, currency):
    for item in data.get("details", []):
        if item.get("ccy") == currency:
            return Decimal(item.get("eq", "0"))

    return Decimal("0")


# =========================
# BTC Price
# =========================

def get_btc_price():
    response = market.get_ticker(instId="BTC-USDT")

    if response.get("code") != "0":
        raise RuntimeError(f"OKX Market Error: {response}")

    ticker = response["data"][0]

    return {
        "last": Decimal(ticker["last"]),
        "bid": Decimal(ticker["bidPx"]),
        "ask": Decimal(ticker["askPx"]),
    }


# =========================
# Main
# =========================

def main():

    account_data = get_account()

    usdt = get_balance(account_data, "USDT")
    btc = get_balance(account_data, "BTC")

    btc_price = get_btc_price()

    print()
    print("=" * 50)
    print("        ADAPTIVE GRID BOT")
    print("             OKX DEMO")
    print("=" * 50)

    print()
    print("API Status      : CONNECTED")

    print()
    print("ACCOUNT")
    print("-" * 50)
    print(f"USDT Balance    : {usdt:,.4f}")
    print(f"BTC Balance     : {btc:,.8f}")

    print()
    print("BTC / USDT")
    print("-" * 50)
    print(f"Last Price      : ${btc_price['last']:,.2f}")
    print(f"Bid             : ${btc_price['bid']:,.2f}")
    print(f"Ask             : ${btc_price['ask']:,.2f}")
    print(f"Spread          : ${btc_price['ask'] - btc_price['bid']:,.2f}")

    print()
    print("=" * 50)
    print("          NO TRADING")
    print("=" * 50)
    print()


if __name__ == "__main__":
    main()