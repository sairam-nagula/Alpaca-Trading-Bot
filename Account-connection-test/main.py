import os
from dotenv import load_dotenv
from alpaca_trade_api.rest import REST

def main():
    load_dotenv()

    API_KEY = os.getenv("APCA_API_KEY_ID")
    SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")
    BASE_URL = os.getenv("APCA_API_BASE_URL")
    print("API Key:", API_KEY)
    print("Secret Key:", SECRET_KEY)
    print("Base URL:", BASE_URL)


    # Connect to Alpaca
    api = REST(API_KEY, SECRET_KEY, BASE_URL)

    # Test connection by getting account info
    account = api.get_account()
    print("Account status:", account.status)
    print("Cash available:", account.cash)


if __name__ == "__main__":
    main()
