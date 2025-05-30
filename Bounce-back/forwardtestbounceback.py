import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# Load credentials
load_dotenv()
API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")
TICKERS = [ticker.strip() for ticker in os.getenv("TICKERS", "").split(",") if ticker.strip()]

trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# Strategy parameters
POSITION_SIZE = 900
DROP_PCT = 4.0
TAKE_PROFIT_PCT = 4.0
STOP_LOSS_PCT = -0.5
HOLD_HOURS_MAX = 72
DROP_LOOKBACK_BARS = 60

UTC_NOW = datetime.now(pytz.UTC)
START_TIME = UTC_NOW - timedelta(minutes=DROP_LOOKBACK_BARS + 2)  # small buffer

positions = {}

for ticker in TICKERS:
    try:
        request = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=TimeFrame.Minute,
            start=START_TIME,
            end=UTC_NOW,
            feed = "iex"
        )
        df = data_client.get_stock_bars(request).df
        if df.empty:
            print(f"No recent data for {ticker}.")
            continue

        prices = df.xs(ticker, level=0)
        now = prices.iloc[-1]
        now_time = now.name
        current_price = now["open"]

        # Check if already in a position
        account_positions = trading_client.get_all_positions()
        active_position = next((p for p in account_positions if p.symbol == ticker), None)

        # SELL CHECK
        if active_position:
            entry_price = float(active_position.avg_entry_price)
            qty = float(active_position.qty)
            time_held = (now_time - datetime.strptime(active_position.asset_class_updated_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=pytz.UTC)).total_seconds() / 3600
            return_pct = (current_price - entry_price) / entry_price * 100

            if return_pct >= TAKE_PROFIT_PCT or return_pct <= STOP_LOSS_PCT or time_held >= HOLD_HOURS_MAX:
                trading_client.submit_order(
                    MarketOrderRequest(
                        symbol=ticker,
                        qty=qty,
                        side=OrderSide.SELL,
                        time_in_force=TimeInForce.DAY
                    )
                )
                print(f"[SELL] {ticker} at ${current_price:.2f} | Return: {return_pct:.2f}%")

        # BUY CHECK
        else:
            window = prices.iloc[-DROP_LOOKBACK_BARS:]
            max_close = window["close"].max()
            drop_pct = (current_price - max_close) / max_close * 100
            sma10 = prices["close"].rolling(10).mean().iloc[-2]
            trend_ok = now["close"] > sma10

            if drop_pct <= -DROP_PCT and trend_ok:
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
                    print(f"[BUY] {ticker} at ${current_price:.2f} | Drop: {drop_pct:.2f}%")

    except Exception as e:
        print(f"Error processing {ticker}: {e}")
