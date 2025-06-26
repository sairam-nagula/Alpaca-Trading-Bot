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
received_tickers = set()
current_minute = None

# === Alpaca Clients ===
trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
stream = StockDataStream(API_KEY, SECRET_KEY)

# === LOGGING SETUP ===
LOG_FILE = "output.log"

def log_message(msg):
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")

# === LOAD OPEN POSITIONS ===
def load_open_positions():
    global position
    try:
        live_positions = trading_client.get_all_positions()
        for pos in live_positions:
            symbol = pos.symbol.upper()
            position[symbol] = {
                "entry_price": float(pos.avg_entry_price),
                "entry_time": datetime.now(pytz.UTC),  # Approximate since API doesn't return this
                "shares": int(pos.qty)
            }
            print(f"[INIT] Loaded open position: {symbol} | Entry: {pos.avg_entry_price} | Shares: {pos.qty}")
            log_message(f"[INIT] Loaded open position: {symbol} | Entry: {pos.avg_entry_price} | Shares: {pos.qty}")
    except Exception as e:
        print(f"[ERROR] Failed to load positions: {e}")
        log_message(f"[ERROR] Failed to load positions: {e}")


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

    if isinstance(bars.index, pd.MultiIndex):
        return bars.xs(ticker, level=0).tail(ROLLING_WINDOW_SIZE)
    else:
        return pd.DataFrame()  # If no data is returned, fallback to empty

# === Trigger Backfill for Missing Tickers ===
async def trigger_backfill():
    await asyncio.sleep(5)  # Wait until about the 5th second of the new minute

    missing_tickers = [ticker for ticker in TICKERS if ticker not in received_tickers]

    if not missing_tickers:
        return

    for ticker in missing_tickers:
        try:
            request = StockBarsRequest(
                symbol_or_symbols=ticker,
                timeframe=TimeFrame.Minute,
                limit=1
            )
            bars = data_client.get_stock_bars(request).df

            if isinstance(bars.index, pd.MultiIndex):
                latest_bar = bars.xs(ticker, level=0).iloc[-1]
            else:
                latest_bar = bars.iloc[-1]

            class Bar:
                def __init__(self, symbol, row):
                    self.symbol = symbol
                    self.timestamp = row.name
                    self.open = row['open']
                    self.high = row['high']
                    self.low = row['low']
                    self.close = row['close']
                    self.volume = row['volume']

            backfill_bar = Bar(ticker, latest_bar)
            process_new_bar(backfill_bar)

            print(f"[BACKFILL] {ticker} backfilled successfully")
            log_message(f"[BACKFILL] {ticker} backfilled successfully")

        except Exception as e:
            print(f"[BACKFILL ERROR] {ticker}: {e}")
            log_message(f"[BACKFILL ERROR] {ticker}: {e}")



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
    global current_minute
    symbol = bar.symbol
    received_tickers.add(symbol)

    # Detect new minute
    bar_minute = bar.timestamp.replace(second=0, microsecond=0)

    if current_minute is None:
        current_minute = bar_minute

    if bar_minute != current_minute:
        # Minute has changed, trigger backfill for the previous minute
        await trigger_backfill()
        received_tickers.clear()
        current_minute = bar_minute

    process_new_bar(bar)


        # Show live return if we hold the stock
    if symbol in position:
        entry_price = position[symbol]["entry_price"]
        entry_time = position[symbol]["entry_time"]
        return_pct = (bar.close - entry_price) / entry_price * 100
        time_held = (bar.timestamp - entry_time).total_seconds() / 3600

        print(f"[LIVE RETURN] [{symbol}] {change_timezone(bar.timestamp)} | Price: {bar.close:.2f} | Return: {return_pct:.2f}% | Held: {time_held:.2f}h")
        log_message(f"[LIVE RETURN] [{symbol}] {change_timezone(bar.timestamp)} | Price: {bar.close:.2f} | Return: {return_pct:.2f}% | Held: {time_held:.2f}h")


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
    load_open_positions()
    for ticker in TICKERS:
        prices_df[ticker] = init_prices_df(ticker)
        stream.subscribe_bars(handle_bar, ticker)

    await stream._run_forever()

if __name__ == "__main__":
    asyncio.run(main())