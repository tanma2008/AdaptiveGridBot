import os
from decimal import Decimal

from dotenv import load_dotenv
import okx.Account as Account


load_dotenv()

FLAG = os.getenv("OKX_FLAG", "1")


account_api = Account.AccountAPI(
    api_key=os.getenv("OKX_API_KEY"),
    api_secret_key=os.getenv("OKX_SECRET_KEY"),
    passphrase=os.getenv("OKX_PASSPHRASE"),
    flag=FLAG,
    debug=False,
)


def get_usdt_balance():

    response = account_api.get_account_balance(
        ccy="USDT"
    )

    if response.get("code") != "0":
        raise RuntimeError(
            f"OKX Account Error: {response}"
        )

    data = response.get("data", [])

    if not data:
        return Decimal("0")

    details = data[0].get("details", [])

    for item in details:

        if item.get("ccy") == "USDT":

            return Decimal(
                item.get("availBal", "0")
            )

    return Decimal("0")


def main():

    print()
    print("=" * 65)
    print("        ADAPTIVE GRID BOT")
    print("          ACCOUNT MANAGER")
    print("=" * 65)

    balance = get_usdt_balance()

    print()
    print(
        f"USDT Available : {balance:.4f}"
    )

    print(
        f"Max Exposure   : "
        f"{balance * Decimal('0.30'):.4f}"
    )

    print()
    print("=" * 65)
    print("              ACCOUNT OK")
    print("=" * 65)


if __name__ == "__main__":
    main()