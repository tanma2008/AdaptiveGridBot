import os
from dotenv import load_dotenv
from okx import Account

load_dotenv()

api_key = os.getenv("OKX_API_KEY")
api_secret = os.getenv("OKX_API_SECRET")
passphrase = os.getenv("OKX_PASSPHRASE")
flag = os.getenv("OKX_FLAG", "1")

if not all([api_key, api_secret, passphrase]):
    raise RuntimeError("Missing OKX API credentials in .env")

print("Connecting to OKX Demo...")

account = Account.AccountAPI(
    api_key=api_key,
    api_secret_key=api_secret,
    passphrase=passphrase,
    flag=flag,
    debug=False,
)

result = account.get_account_balance()

print("OKX response:")
print(result)