import os
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# Load environment variables
load_dotenv()

API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")
TICKERS = os.getenv("TICKERS", "").split(",")

data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# Strategy Parameters (copied from live)
MOMENTUM_THRESHOLD = 0.4            # Avoid micro-noise trades
POSITION_SIZE = 600                 # Keep capital the same
HOLD_DURATION_MINUTES = 10          # Give winners a bit more time
STOP_LOSS_PCT = -1.0                # Let volatile moves breathe
SMA_FAST_WINDOW = 10                 # Slightly smoother trend signal
SMA_SLOW_WINDOW = 20
LOOKBACK_MINUTES = 20               # Match the window to avoid NaNs

# Backtest Time Range
START_DATE = datetime(2024, 4, 1, tzinfo=pytz.UTC)
END_DATE = datetime(2024, 5, 10, tzinfo=pytz.UTC)

def backtest_sma_strategy(symbol):
    print(f"\n--- Backtesting {symbol} ---")

    request_params = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=START_DATE,
        end=END_DATE,
    )

    bars = data_client.get_stock_bars(request_params).data.get(symbol, [])
    if not bars:
        print(f"No data for {symbol}")
        return

    df = pd.DataFrame([{
        "timestamp": bar.timestamp.replace(tzinfo=pytz.UTC),
        "close": bar.close
    } for bar in bars]).set_index("timestamp")

    cash = 10000
    position_qty = 0
    entry_price = None
    last_buy_time = None

    portfolio_values = []
    timestamps = []
    trades = []

    for i in range(LOOKBACK_MINUTES, len(df)):
        window = df.iloc[i - LOOKBACK_MINUTES: i]
        now = df.index[i]
        price = df.iloc[i]["close"]

        window["sma_fast"] = window["close"].rolling(SMA_FAST_WINDOW).mean()
        window["sma_slow"] = window["close"].rolling(SMA_SLOW_WINDOW).mean()

        sma_fast = window["sma_fast"].iloc[-1]
        sma_slow = window["sma_slow"].iloc[-1]
        momentum = ((sma_fast - sma_slow) / sma_slow) * 100 if sma_slow else 0

        if momentum > MOMENTUM_THRESHOLD and position_qty == 0:
            qty = int(POSITION_SIZE / price)
            if qty > 0:
                position_qty = qty
                cash -= qty * price
                entry_price = price
                last_buy_time = now
                trades.append((now, "BUY", price, qty))

        elif position_qty > 0:
            change_pct = ((price - entry_price) / entry_price) * 100
            held_time = now - last_buy_time if last_buy_time else timedelta(0)

            if change_pct <= STOP_LOSS_PCT:
                cash += position_qty * price
                trades.append((now, "STOP-LOSS SELL", price, position_qty))
                position_qty = 0
                entry_price = None
                last_buy_time = None

            elif sma_fast < sma_slow and held_time >= timedelta(minutes=HOLD_DURATION_MINUTES):
                cash += position_qty * price
                trades.append((now, "SMA TIME SELL", price, position_qty))
                position_qty = 0
                entry_price = None
                last_buy_time = None

        portfolio_values.append(cash + position_qty * price)
        timestamps.append(now)

    print(f"Final portfolio value for {symbol}: ${portfolio_values[-1]:.2f}")
    for t in trades:
        print(f"{t[0]} | {t[1]} | ${t[2]:.2f} | {t[3]} shares")

    plt.figure(figsize=(10, 5))
    plt.plot(timestamps, portfolio_values, label=f"{symbol} Portfolio")
    plt.xlabel("Time")
    plt.ylabel("Portfolio Value ($)")
    plt.title(f"Backtest Equity Curve for {symbol}")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

# Run it
for ticker in TICKERS:
    backtest_sma_strategy(ticker)