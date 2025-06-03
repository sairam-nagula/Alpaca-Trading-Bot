import os
import json
from datetime import datetime, timedelta
import pytz
import pandas as pd
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import firebase_admin
from firebase_admin import credentials, firestore

# === STRATEGY PARAMETERS ===
POSITION_SIZE = 10000
DROP_PCT = 4.0
TAKE_PROFIT_PCT = 4.0
STOP_LOSS_PCT = -0.5
HOLD_HOURS_MAX = 72
DROP_LOOKBACK_BARS = 60


# Firebase setup
load_dotenv()
key_str = os.getenv("FIREBASE_KEY")
key_dict = json.loads(key_str)
cred = credentials.Certificate(key_dict)

firebase_admin.initialize_app(cred)
db = firestore.client()
positions_ref = db.collection("positions")


# === SETUP ===
API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")
TICKERS = [t.strip() for t in os.getenv("TICKERS", "").split(",") if t.strip()]

trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

eastern = pytz.timezone("US/Eastern")

def load_position_log():
    docs = positions_ref.stream()
    return {doc.id: doc.to_dict() for doc in docs}


def save_position_log(log):
    for ticker, data in log.items():
        positions_ref.document(ticker).set(data)


def fetch_recent_data(symbol, start, end):
    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
    )
    bars = data_client.get_stock_bars(request).df
    if bars.empty or symbol not in bars.index.get_level_values(0):
        return None
    return bars.xs(symbol, level=0)


def fetch_previous_day_close_data(symbol):
    utc_now = datetime.now(pytz.UTC)
    days_back = 1

    while True:
        prev_day = (utc_now - timedelta(days=days_back)).date()
        start = datetime.combine(prev_day, datetime.min.time(), tzinfo=pytz.UTC) + timedelta(hours=19)  # 3:00 PM ET
        end = datetime.combine(prev_day, datetime.min.time(), tzinfo=pytz.UTC) + timedelta(hours=20)   # 4:00 PM ET

        print(f"[INFO] Attempting previous close data for {symbol} from {start.strftime('%A %Y-%m-%d')}")

        bars = fetch_recent_data(symbol, start, end)
        if bars is not None and not bars.empty:
            return bars

        # Go back one more day (weekend/holiday)
        days_back += 1

        # Safety limit: don't go back more than 5 days
        if days_back > 5:
            print(f"[WARN] Could not find valid previous close data for {symbol} in last 5 days.")
            return None


def evaluate_sell_condition(current_price, now_time, entry_time, entry_price):
    held_hours = (now_time - entry_time).total_seconds() / 3600
    return_pct = (current_price - entry_price) / entry_price * 100
    should_sell = (
        return_pct >= TAKE_PROFIT_PCT or 
        return_pct <= STOP_LOSS_PCT or 
        held_hours >= HOLD_HOURS_MAX
    )
    return should_sell, return_pct, held_hours

def evaluate_buy_condition(prices, i, current_price):
    if i < DROP_LOOKBACK_BARS or i < 10:
        return False, None, None

    window = prices.iloc[i - DROP_LOOKBACK_BARS:i]
    max_close = window["close"].max()
    drop_pct = (current_price - max_close) / max_close * 100
    sma10 = prices["close"].rolling(10).mean().iloc[i - 1]
    trend_ok = prices.iloc[i]["close"] > sma10

    return drop_pct <= -DROP_PCT and trend_ok, drop_pct, sma10

def format_timestamps_for_display(df):
    df_display = df.copy()
    df_display.index = df_display.index.tz_convert(eastern)
    df_display.index = df_display.index.strftime('%Y-%m-%d %I:%M %p')
    return df_display

def process_ticker(ticker, prices, current_position, position_log):
    now = prices.iloc[-1]
    now_time = now.name
    current_price = now["open"]

    print(f"\n========== {ticker} ==========")

    i = len(prices) - 1
    if i >= DROP_LOOKBACK_BARS:
        window = prices.iloc[i - DROP_LOOKBACK_BARS:i]
        max_close = window["close"].max()
        drop_pct = (current_price - max_close) / max_close * 100
        sma10 = prices["close"].rolling(10).mean().iloc[i - 1]
        trend_ok = prices.iloc[i]["close"] > sma10
        recent_drops = (prices["open"] - prices["close"].rolling(DROP_LOOKBACK_BARS).max()) / prices["close"].rolling(DROP_LOOKBACK_BARS).max() * 100
        recent_drops = recent_drops.dropna().tail(5).round(2).to_list()

        print(f"Strategy Snapshot:")
        print(f"  Current Price        : ${current_price:.2f}")
        print(f"  Max Close (60 bars)  : ${max_close:.2f}")
        print(f"  % Drop from Max      : {drop_pct:.2f}%")
        print(f"  SMA-10               : ${sma10:.2f}")
        print(f"  Trend Above SMA10?   : {trend_ok}")
        print(f"  Recent Drop Trend    : {recent_drops}")
    else:
        print("[WARN] Not enough data for full 60-bar analysis.")

    if current_position:
        entry_info = position_log.get(ticker)
        qty = float(current_position.qty)

        if not entry_info:
            print(f"[WARN] {ticker} position exists but not in JSON log.")
            return

        entry_time = datetime.fromisoformat(entry_info["entry_time"])
        entry_price = float(entry_info["entry_price"])

        should_sell, return_pct, held_hours = evaluate_sell_condition(current_price, now_time, entry_time, entry_price)
        print(f"[SELL CHECK] Price: ${current_price:.2f} | Entry: ${entry_price:.2f} | Held: {held_hours:.2f}h | Return: {return_pct:.2f}% | Trigger: {should_sell}")

        if should_sell:
            trading_client.submit_order(
                MarketOrderRequest(
                    symbol=ticker,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY
                )
            )
            print(f"[SELL] {ticker} at ${current_price:.2f} | Return: {return_pct:.2f}%")
            positions_ref.document(ticker).delete()


    else:
        if ticker in position_log:
            print(f"[SKIP] {ticker} in log but not in Alpaca — skipping.")
            return

        should_buy, drop_pct, sma10 = evaluate_buy_condition(prices, i, current_price)
        sma10_display = f"{sma10:.2f}" if sma10 is not None else "N/A"
        print(f"[BUY CHECK] Price: ${current_price:.2f} | Drop: {drop_pct:.2f}% | SMA10: {sma10_display} | Trigger: {should_buy}")

        if should_buy:
            shares = int(POSITION_SIZE // current_price)
            if shares > 0:
                trading_client.submit_order(
                    MarketOrderRequest(
                        symbol=ticker,
                        qty=shares,
                        side=OrderSide.BUY,
                        time_in_force=TimeInForce.DAY
                    )
                )
                position_log[ticker] = {
                    "entry_time": now_time.isoformat(),
                    "entry_price": current_price,
                    "shares": shares
                }
                print(f"[BUY] {ticker} at ${current_price:.2f} | Drop: {drop_pct:.2f}%")


if __name__ == "__main__":
    utc_now = datetime.now(pytz.UTC)
    start_time = utc_now - timedelta(minutes=DROP_LOOKBACK_BARS + 2)

    position_log = load_position_log()
    open_positions = {p.symbol: p for p in trading_client.get_all_positions()}

   


    for ticker in TICKERS:
        try:
            if ticker in position_log and ticker not in open_positions:
                print(f"\n========== {ticker} ==========")
                print(f"[CLEANUP] {ticker} found in log but not in Alpaca — removing stale log entry.")
                del position_log[ticker]
                positions_ref.document(ticker).delete()
                continue  # Skip the rest for this ticker

            prices = fetch_recent_data(ticker, start_time, utc_now)
            if prices is None or len(prices) < DROP_LOOKBACK_BARS:
                now_et = datetime.now(eastern)

                if now_et.hour < 10 or (now_et.hour == 10 and now_et.minute <= 30):
                    prev_close = fetch_previous_day_close_data(ticker)
                    if prev_close is not None and not prev_close.empty:
                        prices = pd.concat([prev_close, prices]) if prices is not None else prev_close
                        print(f"[INFO] Augmented {ticker} with previous close data (pre-10:30 AM)")
                    else:
                        print(f"[SKIP] {ticker} has insufficient data and no previous close to backfill")
                        continue
                else:
                    print(f"[WARN] Missing/incomplete data for {ticker} after 10:30 AM. Retrying fetch...")
                    prices = fetch_recent_data(ticker, start_time, utc_now)  # one retry

                    if prices is None or len(prices) < DROP_LOOKBACK_BARS:
                        print(f"[SKIP] {ticker} still missing data after retry. Skipping.")
                        continue


            active_position = open_positions.get(ticker)
            process_ticker(ticker, prices, active_position, position_log)

        except Exception as e:
            print(f"[ERROR] {ticker}: {e}")

    save_position_log(position_log)
