# Momentum Strategy

import os
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from alpaca_trade_api.rest import REST, TimeFrame

# Load .env file
load_dotenv()

# Alpaca credentials
API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")
BASE_URL = os.getenv("APCA_API_BASE_URL")
TICKERS = os.getenv("TICKERS", "").split(",")

# Alpaca client
client = REST(API_KEY, SECRET_KEY, BASE_URL)

# Strategy parameters
MOMENTUM_THRESHOLD = 2.0  # in %
POSITION_SIZE = 100  # dollars per trade

def get_price_data(symbol):
    end = datetime.now()
    start = end - timedelta(minutes=30)

    # Convert to RFC 3339 format without microseconds
    start_str = start.replace(microsecond=0).isoformat() + "Z"
    end_str = end.replace(microsecond=0).isoformat() + "Z"

    try:
        barset = client.get_bars(symbol, TimeFrame.Minute, start=start_str, end=end_str).df
        return barset

    except Exception as e:
        print(f"Error fetching data for  {symbol}: {e}")
        return pd.DataFrame()


def calculate_momentum(df):
    """
    Calculate the momentum of a stock based on its price data.

    Args:
        df (pd.DataFrame): A DataFrame containing the stock price data with at least a 'close' column.

    Returns:
        float: The momentum percentage calculated over the period covered by the DataFrame.
               Returns 0 if the DataFrame has less than 2 data points.
    """

    if len(df) < 2:
        return 0
    return ((df['close'].iloc[-1] - df['close'].iloc[0]) / df['close'].iloc[0]) * 100

def get_position(symbol):
    """
    Returns the quantity of the position for a given symbol.
    If no position exists, returns 0.
    """
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
    """
    Run the momentum strategy on the given tickers.

    This function will:

    1. Fetch the latest 10 minutes of price data for each ticker.
    2. Calculate the momentum of the stock over the last 10 minutes.
    3. If the momentum is above the threshold and the current volume is higher than the average volume and there is no position, buy the stock.
    4. If the momentum is below 0 and there is a position, sell the stock.

    The threshold, position size, and tickers are set at the top of the file.
    """
    for symbol in TICKERS:
        print(f"\nChecking {symbol}...")
        df = get_price_data(symbol)
        if df.empty:
            continue

        momentum = calculate_momentum(df)
        latest_close = df['close'].iloc[-1]
        volume = df['volume'].iloc[-1]
        avg_volume = df['volume'].mean()
        position_qty = get_position(symbol)

        print(f"Momentum: {momentum:.2f}% | Volume: {volume} | Avg Vol: {avg_volume:.0f} | Current Qty: {position_qty}")

        if momentum > MOMENTUM_THRESHOLD and volume > avg_volume and position_qty == 0:
            qty = int(POSITION_SIZE / latest_close)
            place_order(symbol, "buy", qty)

        elif momentum < 0 and position_qty > 0:
            place_order(symbol, "sell", int(position_qty))

    

if __name__ == "__main__":
    run_strategy()
