import os
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import pytz

# Load environment
load_dotenv()
API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")
TICKERS = os.getenv("TICKERS", "").split(",")

# Alpaca Historical Client
client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# Backtest parameters
START_DATE = datetime(2024, 5, 1, tzinfo=pytz.UTC)
END_DATE = datetime(2024, 5, 15, tzinfo=pytz.UTC)
POSITION_SIZE = 200      # dollars per trade
MOMENTUM_THRESHOLD = 0.1  # in %
COOLDOWN_MINUTES = 10

def backtest(symbol):
    print(f"\n--- Backtesting {symbol} ---")
    
    # Request minute-level data
    request_params = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=START_DATE,
        end=END_DATE,
    )

    bars = client.get_stock_bars(request_params).df
    if bars.empty:
        print("No data for", symbol)
        return

    # Isolate the data for our symbol and sort by time if needed
    df = bars.xs(symbol, level=0).sort_index()

    # Initialize simulation variables
    cash = 10000.0
    position = 0
    last_buy_time = None
    cooldown = timedelta(minutes=COOLDOWN_MINUTES)
    trade_log = []
    timestamps = []
    portfolio_values = []

    # Run through each minute in the dataframe
    for i in range(1, len(df)):
        current_time = df.index[i]
        price_now = df.iloc[i]['close']
        price_then = df.iloc[i - 1]['close']
        momentum = ((price_now - price_then) / price_then) * 100

        # Check if we should sell: if momentum is negative and we have a position
        if position > 0 and momentum <= 0:
            cash += position * price_now
            trade_log.append((current_time, "SELL", price_now, position))
            position = 0
            last_buy_time = None

        # Check if we should buy: if momentum is above the threshold and no position
        elif position == 0 and momentum > MOMENTUM_THRESHOLD:
            if (last_buy_time is None) or ((current_time - last_buy_time) >= cooldown):
                shares = int(POSITION_SIZE / price_now)
                if shares > 0:
                    cash -= shares * price_now
                    position = shares
                    trade_log.append((current_time, "BUY", price_now, shares))
                    last_buy_time = current_time

        # Calculate portfolio value for this minute
        portfolio_value = cash + position * price_now
        timestamps.append(current_time)
        portfolio_values.append(portfolio_value)

    # Final portfolio value
    final_value = portfolio_values[-1]
    print(f"Final portfolio value for {symbol}: ${final_value:.2f}")
    print(f"Number of trades: {len(trade_log)}")
    for t in trade_log:
        print(f"{t[0]} | {t[1]} | ${t[2]:.2f} | {t[3]} shares")

    # Plot the equity curve
    plt.figure(figsize=(10, 5))
    plt.plot(timestamps, portfolio_values, label=f'{symbol} Portfolio Value')
    plt.xlabel('Time')
    plt.ylabel('Portfolio Value ($)')
    plt.title(f'Equity Curve for {symbol}')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

# Run backtest for each ticker
for ticker in TICKERS:
    backtest(ticker)