
import os
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from alpaca_trade_api.rest import REST, TimeFrame
from datetime import timezone

# Load .env variables
load_dotenv()

# Alpaca credentials
API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")
BASE_URL = os.getenv("APCA_API_BASE_URL")
TICKERS = os.getenv("TICKERS", "").split(",")

# Alpaca client
client = REST(API_KEY, SECRET_KEY, BASE_URL)

# Strategy parameters
MOMENTUM_THRESHOLD = 0.25  # in %
POSITION_SIZE = 100        # dollars per trade
LOOKBACK_MINUTES = 2       # fetch 2 minutes of bars
COOLDOWN_MINUTES = 5       # wait time between buys per ticker

# In-memory tracking of last buy timestamps
last_buy_time = {}

def get_price_data(symbol):
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=LOOKBACK_MINUTES)

    try:
        barset = client.get_bars(symbol, TimeFrame.Minute, limit=2, feed="iex").df

        if barset.empty:
            print(f"No data for {symbol}")
        return barset
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return pd.DataFrame()

def calculate_momentum(df):
    if len(df) < 2:
        return 0
    return ((df['close'].iloc[-1] - df['close'].iloc[0]) / df['close'].iloc[0]) * 100

def get_position(symbol):
    try:
        position = client.get_position(symbol)
        return float(position.qty)
    except:
        return 0.0

def place_order(symbol, side, qty):
    print(f"Placing {side} order for {qty} shares of {symbol}")
    client.submit_order(
        symbol=symbol,
        qty=qty,
        side=side,
        type="market",
        time_in_force="gtc"
    )

def run_strategy():
    current_time = datetime.now(timezone.utc)


    for symbol in TICKERS:
        print(f"\nChecking {symbol}...")
        df = get_price_data(symbol)
        if df.empty or len(df) < 2:
            continue

        momentum = calculate_momentum(df)
        latest_close = df['close'].iloc[-1]
        position_qty = get_position(symbol)

        print(f"Momentum: {momentum:.2f}% | Price: {latest_close:.2f} | Current Qty: {position_qty}")

        # Check cooldown
        if symbol in last_buy_time:
            elapsed = (current_time - last_buy_time[symbol]).total_seconds() / 60
            if elapsed < COOLDOWN_MINUTES:
                print(f"Cooldown active for {symbol} ({elapsed:.1f} mins since last buy)")
                continue

        # Buy condition
        if momentum > MOMENTUM_THRESHOLD and position_qty == 0:
            qty = int(POSITION_SIZE / latest_close)
            place_order(symbol, "buy", qty)
            last_buy_time[symbol] = current_time

        # Sell condition
        elif momentum <= 0 and position_qty > 0:
            place_order(symbol, "sell", int(position_qty))
            if symbol in last_buy_time:
                del last_buy_time[symbol]

if __name__ == "__main__":
    run_strategy()