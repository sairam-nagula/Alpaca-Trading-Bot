import os
import pandas as pd
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# Load environment
load_dotenv()
API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")
symbol = "HIMS"

# Initialize Alpaca client
client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# Fetch recent data (last 90 minutes for margin)
utc_now = datetime.now(pytz.UTC)
start_time = utc_now - timedelta(minutes=90)

request = StockBarsRequest(
    symbol_or_symbols=symbol,
    timeframe=TimeFrame.Minute,
    start=start_time,
    end=utc_now,
)

bars = client.get_stock_bars(request).df
if bars.empty:
    print("[ERROR] No data returned for HIMS.")
else:
    df = bars.xs(symbol, level=0)
    df.index = df.index.tz_convert("US/Eastern")  # Convert to ET
    df["sma10"] = df["close"].rolling(10).mean()
    df["drop_from_max"] = (df["open"] - df["close"].rolling(60).max()) / df["close"].rolling(60).max() * 100

    print(df.tail(15)[["open", "close", "sma10", "drop_from_max"]])
