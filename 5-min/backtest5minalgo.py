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

# Strategy Parameters
STARTING_CASH = 10000
MOMENTUM_THRESHOLD = 0.4
POSITION_SIZE = 1000
HOLD_DURATION_MINUTES = 20
TAKE_PROFIT_PCT = 3.5
SMA_FAST_WINDOW = 8
SMA_SLOW_WINDOW = 20
LOOKBACK_MINUTES = 20
ATR_WINDOW = 14
ATR_MULTIPLIER = 1.5  # For dynamic stop loss

START_DATE = datetime(2025, 3, 1, tzinfo=pytz.UTC)
END_DATE = datetime(2025, 4, 24, tzinfo=pytz.UTC)

# Globals
final_portfolios = []

def plot_portfolio(timestamps, portfolio_values, symbol):
    final_value = portfolio_values[-1]
    plt.figure(figsize=(10, 5))
    plt.plot(timestamps, portfolio_values, label=f"{symbol} Portfolio")
    plt.xlabel("Time")
    plt.ylabel("Portfolio Value ($)")
    plt.title(f"Final portfolio value for {symbol}: ${final_value:.2f}")
    plt.ticklabel_format(useOffset=False, style='plain', axis='y')
    plt.gca().get_yaxis().set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

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

    df = pd.DataFrame([{ "timestamp": bar.timestamp.replace(tzinfo=pytz.UTC), "close": bar.close } for bar in bars]).set_index("timestamp")
    df["tr"] = df["close"].diff().abs()
    df["atr"] = df["tr"].rolling(window=ATR_WINDOW).mean()

    cash = STARTING_CASH
    position_qty = 0
    entry_price = None
    entry_atr = None
    last_buy_time = None
    cooldown_minutes = 10
    next_entry_allowed = df.index[0]
    trade_count = 0
    MAX_TRADES_PER_DAY = 3

    portfolio_values = []
    timestamps = []
    trades = []

    for i in range(LOOKBACK_MINUTES, len(df)):
        window = df.iloc[i - LOOKBACK_MINUTES + 1: i + 1].copy()
        now = df.index[i]
        price = df.iloc[i]["close"]

        if now < next_entry_allowed:
            portfolio_values.append(cash + position_qty * price)
            timestamps.append(now)
            continue

        window["sma_fast"] = window["close"].rolling(SMA_FAST_WINDOW).mean()
        window["sma_slow"] = window["close"].rolling(SMA_SLOW_WINDOW).mean()

        sma_fast = window["sma_fast"].iloc[-1]
        sma_slow = window["sma_slow"].iloc[-1]
        atr = df["atr"].iloc[i]
        momentum = ((sma_fast - sma_slow) / sma_slow) * 100 if sma_slow else 0
        recent_high = df["close"].iloc[i - LOOKBACK_MINUTES:i].max()

        if momentum > MOMENTUM_THRESHOLD and price > recent_high and position_qty == 0 and trade_count < MAX_TRADES_PER_DAY:
            qty = int(POSITION_SIZE / price)
            if qty > 0:
                position_qty = qty
                entry_price = price
                entry_atr = atr
                last_buy_time = now
                cash -= qty * price
                next_entry_allowed = now + timedelta(minutes=cooldown_minutes)
                trade_count += 1
                trades.append((now, "BUY", price, qty))

        elif position_qty > 0:
            change_pct = ((price - entry_price) / entry_price) * 100
            held_time = now - last_buy_time if last_buy_time else timedelta(0)
            dynamic_stop_loss_pct = -ATR_MULTIPLIER * entry_atr / entry_price * 100

            if change_pct <= dynamic_stop_loss_pct:
                cash += position_qty * price
                trades.append((now, "DYNAMIC STOP SELL", price, position_qty))
                position_qty = 0
                entry_price = None
                last_buy_time = None
                next_entry_allowed = now + timedelta(minutes=cooldown_minutes)

            elif change_pct >= TAKE_PROFIT_PCT:
                cash += position_qty * price
                trades.append((now, "TAKE-PROFIT SELL", price, position_qty))
                position_qty = 0
                entry_price = None
                last_buy_time = None
                next_entry_allowed = now + timedelta(minutes=cooldown_minutes)

            elif sma_fast < sma_slow and held_time >= timedelta(minutes=HOLD_DURATION_MINUTES):
                cash += position_qty * price
                trades.append((now, "SMA TIME SELL", price, position_qty))
                position_qty = 0
                entry_price = None
                last_buy_time = None
                next_entry_allowed = now + timedelta(minutes=cooldown_minutes)

        portfolio_values.append(cash + position_qty * price)
        timestamps.append(now)

    final_value = portfolio_values[-1]
    final_portfolios.append(final_value)

    print(f"Final portfolio value for {symbol}: ${final_value:.2f}")
    for t in trades:
        print(f"{t[0]} | {t[1]} | ${t[2]:.2f} | {t[3]} shares")

    # Toggle this line on/off to show or hide charts
    # plot_portfolio(timestamps, portfolio_values, symbol)

# Run backtest
for ticker in TICKERS:
    backtest_sma_strategy(ticker)

# Final summary
total_final_value = sum(final_portfolios)
total_invested = STARTING_CASH * len(final_portfolios)
total_profit = total_final_value - total_invested
total_pct_change = (total_profit / total_invested) * 100

print("\n--- Total P&L Summary ---")
print(f"Total Final Value: ${total_final_value:,.2f}")
print(f"Total Invested:    ${total_invested:,.2f}")
print(f"Total Net P&L:     ${total_profit:,.2f}")
print(f"Total % Change:    {total_pct_change:.2f}%")
