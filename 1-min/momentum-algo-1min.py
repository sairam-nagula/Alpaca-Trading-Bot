import os
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pytz
from alpaca_trade_api.rest import REST
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# Load .env variables
load_dotenv()

# Alpaca credentials
API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")
BASE_URL = os.getenv("APCA_API_BASE_URL")
TICKERS = os.getenv("TICKERS", "").split(",")

# Alpaca clients
client = REST(API_KEY, SECRET_KEY, BASE_URL)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# Strategy parameters
MOMENTUM_THRESHOLD = 0.15  # in %
POSITION_SIZE = 600  # dollars per trade
LOOKBACK_MINUTES = 2  # fetch 2 minutes of bars
LOOKBACK_MINUTES_2 = 3

# In-memory tracking of last buy timestamps
last_buy_time = {}


def get_price_data(symbol):
    end = datetime.utcnow()
    start = end - timedelta(minutes=LOOKBACK_MINUTES)
    start_2 = end - timedelta(minutes=LOOKBACK_MINUTES_2)

    request_params = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        feed="iex",
    )
    request_params2 = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame.Minute,
        start=start_2,
        end=end,
        feed="iex",
    )

    try:
        bars = data_client.get_stock_bars(request_params).data[symbol]
        bars2 = data_client.get_stock_bars(request_params2).data[symbol]

        if not bars2:
            print(f"No data returned for {symbol}")
            return pd.DataFrame()

        if not bars:
            print(f"No data returned for {symbol}")
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame(
            [
                {
                    "timestamp": bar.timestamp.replace(tzinfo=pytz.utc).astimezone(
                        pytz.timezone("America/New_York")
                    ),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
                for bar in bars
            ]
        )
        df2 = pd.DataFrame(
            [
                {
                    "timestamp": bar.timestamp.replace(tzinfo=pytz.utc).astimezone(
                        pytz.timezone("America/New_York")
                    ),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
                for bar in bars2
            ]
        )
        return df, df2

    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return pd.DataFrame(), pd.DataFrame()  



def calculate_momentum(df, df2):
    try:
        latest_close = df["close"].iloc[-1]
        earlier_close = df2["close"].iloc[0]
        momentum = ((latest_close - earlier_close) / earlier_close) * 100
        return momentum
    except Exception as e:
        print(f"Error calculating momentum: {e}")
        return 0


def get_position(symbol):
    try:
        position = client.get_position(symbol)
        return float(position.qty)
    except:
        return 0.0


def place_order(symbol, side, qty):
    print(f"Placing {side} order for {qty} shares of {symbol}")
    client.submit_order(
        symbol=symbol, qty=qty, side=side, type="market", time_in_force="gtc"
    )


def run_strategy():
    current_time = datetime.now(pytz.utc)

    for symbol in TICKERS:
        print(f"\nChecking {symbol}...")
        df, df2 = get_price_data(symbol)
        if df.empty or df2.empty:
            print(f"No data returned for {symbol}")
            continue

        momentum = calculate_momentum(df, df2)
        latest_close = df["close"].iloc[-1]
        position_qty = get_position(symbol)
        timestamp = df["timestamp"].iloc[-1].strftime("%H:%M:%S")

        print(
            f"Time: {timestamp} | Momentum: {momentum:.2f}% | Price: {latest_close:.2f} | Current Qty: {position_qty}"
        )

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
