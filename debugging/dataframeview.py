import os
import pandas as pd
from datetime import datetime
import pytz
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest, StockLatestTradeRequest, StockLatestBarRequest
from alpaca.data.timeframe import TimeFrame


# Load environment variables
load_dotenv()
API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")

# List of tickers
TICKERS = ["HIMS"]  # Add more as needed

# Initialize Alpaca data client
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# Time range
START_DATE = datetime(2025, 6, 11, tzinfo=pytz.UTC)
END_DATE = datetime(2025, 6, 12, tzinfo=pytz.UTC)

def fetch_minute_data(symbol, start, end):
    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        feed="sip"
    )
    bars = data_client.get_stock_bars(request).df
    if isinstance(bars, pd.DataFrame) and not bars.empty:
        return bars[bars.index.get_level_values("symbol") == symbol].copy()
    else:
        return pd.DataFrame()

# Fetch data for all tickers and combine
all_data = []
for ticker in TICKERS:
    df = fetch_minute_data(ticker, START_DATE, END_DATE)
    if not df.empty:
        all_data.append(df)

combined_df = pd.concat(all_data) if all_data else pd.DataFrame()

# === Print Historical Minute Bars (last 5 rows) ===
print("=== LAST 5 MINUTE BARS (REST) ===")
print(combined_df.tail(5))

# === Print Latest Quote and Trade (per ticker) ===
print("\n=== LIVE QUOTE AND TRADE DATA (REST) ===")

for ticker in TICKERS:
    latest_quote_resp = data_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=ticker))
    latest_trade_resp = data_client.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=ticker))

    latest_quote = latest_quote_resp[ticker]
    latest_trade = latest_trade_resp[ticker]

    print(f"\nTicker: {ticker}")
    print("Latest Quote:")
    print(f"  Bid:  {latest_quote.bid_price} x {latest_quote.bid_size}")
    print(f"  Ask:  {latest_quote.ask_price} x {latest_quote.ask_size}")
    print("Latest Trade:")
    print(f"  Price: {latest_trade.price}")
    print(f"  Size:  {latest_trade.size}")
    print(f"  Time:  {latest_trade.timestamp}")



from alpaca.data.requests import StockLatestBarRequest

# === Print Latest In-Progress Bar (REST) ===
print("\n=== LATEST BAR (LIVE) ===")

for ticker in TICKERS:
    latest_bar_resp = data_client.get_stock_latest_bar(StockLatestBarRequest(symbol_or_symbols=ticker))
    latest_bar = latest_bar_resp[ticker]

    print(f"\nTicker: {ticker}")
    print(f"  Time:   {latest_bar.timestamp}")
    print(f"  Open:   {latest_bar.open}")
    print(f"  High:   {latest_bar.high}")
    print(f"  Low:    {latest_bar.low}")
    print(f"  Close:  {latest_bar.close}")
    print(f"  Volume: {latest_bar.volume}")

from alpaca.data.requests import StockSnapshotRequest

# === Print Full Snapshot Data (REST) ===
print("\n=== FULL SNAPSHOT DATA (REST) ===")

snapshot_resp = data_client.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=TICKERS))

for ticker in TICKERS:
    snapshot = snapshot_resp[ticker]

    print(f"\nTicker: {ticker}")
    print("Latest Trade:")
    print(f"  Price: {snapshot.latest_trade.price}")
    print(f"  Size:  {snapshot.latest_trade.size}")
    print(f"  Time:  {snapshot.latest_trade.timestamp}")

    print("Latest Quote:")
    print(f"  Bid:  {snapshot.latest_quote.bid_price} x {snapshot.latest_quote.bid_size}")
    print(f"  Ask:  {snapshot.latest_quote.ask_price} x {snapshot.latest_quote.ask_size}")

    print("Latest Minute Bar:")
    print(f"  Time:   {snapshot.minute_bar.timestamp}")
    print(f"  Open:   {snapshot.minute_bar.open}")
    print(f"  High:   {snapshot.minute_bar.high}")
    print(f"  Low:    {snapshot.minute_bar.low}")
    print(f"  Close:  {snapshot.minute_bar.close}")
    print(f"  Volume: {snapshot.minute_bar.volume}")

    print("Latest Daily Bar:")
    print(f"  Open:   {snapshot.daily_bar.open}")
    print(f"  Close:  {snapshot.daily_bar.close}")

    print("Previous Daily Bar:")
    print(f"  Open:   {snapshot.previous_daily_bar.open}")
    print(f"  Close:  {snapshot.previous_daily_bar.close}")
