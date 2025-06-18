import os
import pandas as pd
import numpy as np
import pytz
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.live import StockDataStream
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# === CONFIGURATION ===
load_dotenv()
API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")
TICKERS = [ticker.strip() for ticker in os.getenv("TICKERS", "").split(",") if ticker.strip()]
DROP_PCT = 3
TAKE_PROFIT_PCT = 2
STOP_LOSS_PCT = -0.35
HOLD_HOURS_MAX = 72
DROP_LOOKBACK_BARS = 60
ROLLING_WINDOW_SIZE = DROP_LOOKBACK_BARS + 10
POSITION_SIZE = 20000

# === GLOBAL STATE ===
position = {}
prices_df = {}
eastern = pytz.timezone('US/Eastern')

# === Alpaca Clients ===
trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
stream = StockDataStream(API_KEY, SECRET_KEY)

# === LOGGING SETUP ===
LOG_FILE = "output.log"

def log_message(msg):
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")


# === Initialize DF with Historical Bars ===
def init_prices_df(ticker) -> pd.DataFrame:
    end = datetime.now(pytz.UTC)
    start = end - timedelta(minutes=ROLLING_WINDOW_SIZE + 5)
    request = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
    )
    bars = data_client.get_stock_bars(request).df
    return bars.xs(ticker, level=0).tail(ROLLING_WINDOW_SIZE)

# === Strategy Logic on New Bar ===
def process_new_bar(new_bar):
    global prices_df, position
    symbol = new_bar.symbol

    if symbol not in prices_df:
        prices_df[symbol] = pd.DataFrame()

    new_row = pd.DataFrame([{
        "timestamp": new_bar.timestamp,
        "open": new_bar.open,
        "high": new_bar.high,
        "low": new_bar.low,
        "close": new_bar.close,
        "volume": new_bar.volume
    }]).set_index("timestamp")

    prices_df[symbol] = pd.concat([prices_df[symbol], new_row])
    prices_df[symbol] = prices_df[symbol].tail(ROLLING_WINDOW_SIZE)

    if len(prices_df[symbol]) < DROP_LOOKBACK_BARS + 1:
        return

    current_time = new_bar.timestamp
    current_price = new_bar.close
    signal_candle = prices_df[symbol].iloc[-1]
    prev_window = prices_df[symbol].iloc[-(DROP_LOOKBACK_BARS + 1):-1]

    if symbol in position:
        entry_price = position[symbol]["entry_price"]
        time_held = (current_time - position[symbol]["entry_time"]).total_seconds() / 3600
        return_pct = (current_price - entry_price) / entry_price * 100

        if return_pct >= TAKE_PROFIT_PCT or return_pct <= STOP_LOSS_PCT or time_held >= HOLD_HOURS_MAX:
            print(f"[SELL] [{symbol}] {change_timezone(current_time)} | Price: {current_price:.2f} | Return: {return_pct:.2f}%")
            log_message(
                f"[SELL] [{symbol}] {change_timezone(current_time)} | Price: {current_price:.2f} | Return: {return_pct:.2f}%"
            )
            trading_client.submit_order(
                MarketOrderRequest(
                    symbol=symbol,
                    qty=int(position[symbol]["shares"]),
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY
                )
            )
            del position[symbol]
    else:
        max_high = prev_window["high"].max()
        drop_pct = (signal_candle["close"] - max_high) / max_high * 100
        sma10 = prices_df[symbol]["close"].rolling(10).mean().iloc[-1]
        trend_ok = signal_candle["close"] > sma10

        if drop_pct <= -DROP_PCT and trend_ok:
            shares_to_buy = int(POSITION_SIZE / current_price)
            if shares_to_buy > 0:
                print(f"[BUY] [{symbol}] {change_timezone(current_time)} | Price: {current_price:.2f} | Drop: {drop_pct:.2f}% ")
                log_message(
                    f"[BUY] [{symbol}] {change_timezone(current_time)} | Price: {current_price:.2f} | Drop: {drop_pct:.2f}% "
                )
                trading_client.submit_order(
                    MarketOrderRequest(
                        symbol=symbol,
                        qty=shares_to_buy,
                        side=OrderSide.BUY,
                        time_in_force=TimeInForce.DAY
                    )
                )
                position[symbol] = {
                    "entry_time": current_time,
                    "entry_price": current_price,
                    "shares": shares_to_buy
                }

# === Time Formatting ===
def change_timezone(timestamp):
    local_time = timestamp.astimezone(eastern)
    return local_time.strftime("%m-%d %I:%M %p")

# === Websocket Handler ===
async def handle_bar(bar):
    symbol = bar.symbol
    process_new_bar(bar)

    # Ensure data is long enough
    if symbol not in prices_df or len(prices_df[symbol]) < DROP_LOOKBACK_BARS + 1:
        return

    # Calculate % drop from peak
    prev_window = prices_df[symbol].iloc[-(DROP_LOOKBACK_BARS + 1):-1]
    max_high = prev_window["high"].max()
    drop_pct = (bar.close - max_high) / max_high * 100

    # Compare to SMA10
    sma10 = prices_df[symbol]["close"].rolling(10).mean().iloc[-1]
    above_sma = "yes" if bar.close > sma10 else "no"

    # Format and print
    formatted_time = change_timezone(bar.timestamp)
    print(
        f"[{symbol}] {formatted_time}\n"
        f"       High: {max_high:.2f} | Close: {bar.close:.2f}\n "
        f"      Drop: {drop_pct:.2f}% | Above sma10: {above_sma}"
    )
    log_message(
        f"[{symbol}] {formatted_time}\n"
        f"       High: {max_high:.2f} | Close: {bar.close:.2f}\n "
        f"      Drop: {drop_pct:.2f}% | Above sma10: {above_sma}"
    )

# === Run ===
async def main():
    global prices_df
    for ticker in TICKERS:
        prices_df[ticker] = init_prices_df(ticker)
        stream.subscribe_bars(handle_bar, ticker)

    await stream._run_forever()

if __name__ == "__main__":
    asyncio.run(main())