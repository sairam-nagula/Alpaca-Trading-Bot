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
POSITION_SIZE = 1000  # dollars per trade
HOLD_DURATION_MINUTES = 15
STOP_LOSS_PCT = -2.0  # in %

SMA_FAST_WINDOW = 3
SMA_SLOW_WINDOW = 6
LOOKBACK_MINUTES = 15  # bar data range

def get_price_data(symbol):
    end = datetime.utcnow()
    start = end - timedelta(minutes=LOOKBACK_MINUTES)

    request_params = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        feed="iex",
    )

    try:
        bars = data_client.get_stock_bars(request_params).data[symbol]
        if not bars:
            print(f"No data returned for {symbol}")
            return pd.DataFrame()

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
        return df

    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return pd.DataFrame()


def calculate_sma_momentum(df):
    try:
        df["sma_fast"] = df["close"].rolling(SMA_FAST_WINDOW).mean()
        df["sma_slow"] = df["close"].rolling(SMA_SLOW_WINDOW).mean()
        latest_fast = df["sma_fast"].iloc[-1]
        latest_slow = df["sma_slow"].iloc[-1]

        momentum = ((latest_fast - latest_slow) / latest_slow) * 100
        return momentum, df["close"].iloc[-1], latest_fast, latest_slow
    except Exception as e:
        print(f"Error calculating SMA momentum: {e}")
        return 0, 0, 0, 0


def get_position(symbol):
    try:
        position = client.get_position(symbol)
        return float(position.qty)
    except:
        return 0.0


def get_entry_price(symbol):
    try:
        position = client.get_position(symbol)
        return float(position.avg_entry_price)
    except:
        return None


def get_last_buy_time(symbol):
    try:
        orders = client.list_orders(
            status="filled",
            limit=10,
            direction="desc"
        )
        for order in orders:
            if order.symbol == symbol and order.side == "buy":
                return order.filled_at.replace(tzinfo=pytz.utc)
    except Exception as e:
        print(f"Error getting last buy time for {symbol}: {e}")
    return None


def place_order(symbol, side, qty):
    print(f"Placing {side.upper()} order for {qty} shares of {symbol}")
    client.submit_order(
        symbol=symbol, qty=qty, side=side, type="market", time_in_force="gtc"
    )


def run_strategy():
    current_time = datetime.now(pytz.utc)

    for symbol in TICKERS:
        print(f"\nChecking {symbol}...")
        df = get_price_data(symbol)
        if df.empty:
            continue

        momentum, latest_close, sma_fast, sma_slow = calculate_sma_momentum(df)
        position_qty = get_position(symbol)
        timestamp = df["timestamp"].iloc[-1].strftime("%H:%M:%S")

        print(
            f"Time: {timestamp} | Momentum: {momentum:.2f}% | Price: {latest_close:.2f} | Fast SMA: {sma_fast:.2f} | Slow SMA: {sma_slow:.2f} | Qty: {position_qty}"
        )

        # Buy condition
        if momentum > MOMENTUM_THRESHOLD and position_qty == 0:
            qty = int(POSITION_SIZE / latest_close)
            place_order(symbol, "buy", qty)

        # Sell condition
        elif position_qty > 0:
            entry_price = get_entry_price(symbol)
            if entry_price:
                change_pct = ((latest_close - entry_price) / entry_price) * 100

                # Stop-loss check
                if change_pct <= STOP_LOSS_PCT:
                    print(f"{symbol}: Stop-loss triggered ({change_pct:.2f}%). Selling...")
                    place_order(symbol, "sell", int(position_qty))
                    continue

            # Time-based sell condition
            if sma_fast < sma_slow:
                last_buy = get_last_buy_time(symbol)
                if last_buy:
                    elapsed = current_time - last_buy
                    if elapsed >= timedelta(minutes=HOLD_DURATION_MINUTES):
                        place_order(symbol, "sell", int(position_qty))


if __name__ == "__main__":
    run_strategy()
