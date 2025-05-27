import os
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# Load API keys and environment variables
load_dotenv()
API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")
TICKERS = [ticker.strip() for ticker in os.getenv("TICKERS", "").split(",") if ticker.strip()]

# Alpaca client
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# Strategy parameters
STARTING_CASH = 10000
POSITION_SIZE = 600
DROP_PCT = 4.0
TAKE_PROFIT_PCT = 3.0  # reduced for higher win rate
STOP_LOSS_PCT = -1.0
HOLD_HOURS_MAX = 72
DROP_LOOKBACK_BARS = 60  # reduced for quicker entry

# Backtest settings
START_DATE = datetime(2025, 4, 1, tzinfo=pytz.UTC)
END_DATE = datetime(2025, 5, 1, tzinfo=pytz.UTC)  # Shorter range for minute data

def fetch_minute_data(symbol, start, end):
    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end
    )
    bars = data_client.get_stock_bars(request).df
    return bars.xs(symbol, level=0)

def run_backtest(prices):
    cash = STARTING_CASH
    position = None
    trades = []

    for i in range(DROP_LOOKBACK_BARS, len(prices)):
        now = prices.iloc[i]
        now_time = now.name
        current_price = now["low"]  # use low for entry precision

        if position:
            entry_price = position["entry_price"]
            time_held = (now_time - position["entry_time"]).total_seconds() / 3600
            return_pct = (current_price - entry_price) / entry_price * 100

            if return_pct >= TAKE_PROFIT_PCT or return_pct <= STOP_LOSS_PCT or time_held >= HOLD_HOURS_MAX:
                shares = position["shares"]
                cash += shares * current_price
                trades.append({
                    "buy_time": position["entry_time"],
                    "buy_price": entry_price,
                    "sell_time": now_time,
                    "sell_price": current_price,
                    "return_pct": return_pct
                })
                position = None

        elif not position:
            window = prices.iloc[i - DROP_LOOKBACK_BARS:i]
            max_close = window["close"].max()
            drop_pct = (current_price - max_close) / max_close * 100

            sma_30 = prices["close"].rolling(30).mean().iloc[i]
            trend_ok = now["close"] > sma_30

            if drop_pct <= -DROP_PCT and trend_ok:
                shares_to_buy = POSITION_SIZE / current_price
                cash -= shares_to_buy * current_price
                position = {
                    "entry_time": now_time,
                    "entry_price": current_price,
                    "shares": shares_to_buy
                }

    return cash, trades

def plot_trades(prices, trades, ticker):
    plt.figure(figsize=(14, 6))
    plt.plot(prices.index, prices["close"], label="Price", alpha=0.8)

    for trade in trades:
        plt.scatter(trade["buy_time"], trade["buy_price"], marker="^", color="green", label="Buy", zorder=5)
        plt.scatter(trade["sell_time"], trade["sell_price"], marker="v", color="red", label="Sell", zorder=5)

    plt.title(f"{ticker} Backtest — Buy -{DROP_PCT}%, Sell +{TAKE_PROFIT_PCT}%")
    plt.xlabel("Datetime")
    plt.ylabel("Price")
    plt.grid(True)
    plt.legend(["Price", "Buy", "Sell"])
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    all_trades = []
    combined_final_value = STARTING_CASH

    for TICKER in TICKERS:
        print(f"\n=== Running Backtest for {TICKER} ===")
        try:
            prices = fetch_minute_data(TICKER, START_DATE, END_DATE)
            if prices.empty:
                print(f"No data for {TICKER}, skipping.")
                continue

            cash, trades = run_backtest(prices)
            combined_final_value += cash - STARTING_CASH
            all_trades.extend(trades)

            print(f"\n--- Backtest Result for {TICKER} ---")
            print(f"Final Portfolio Value: ${cash:.2f}")
            print(f"Total Trades: {len(trades)}\n")
            for trade in trades:
                print(f"{trade['buy_time']} BUY @ ${trade['buy_price']:.2f} → "
                      f"{trade['sell_time']} SELL @ ${trade['sell_price']:.2f} | "
                      f"Return: {trade['return_pct']:.2f}%")

            # plot_trades(prices, trades, TICKER)  # Optional visualization

        except Exception as e:
            print(f"Error while processing {TICKER}: {e}")

    print("\n=== TOTAL STRATEGY SUMMARY ===")
    total_trades = len(all_trades)
    if total_trades > 0:
        total_return_pct = sum([t['return_pct'] for t in all_trades])
        avg_return = total_return_pct / total_trades
        wins = sum([1 for t in all_trades if t['return_pct'] > 0])
        win_rate = (wins / total_trades) * 100

        print(f"Total Trades: {total_trades}")
        print(f"Average Return per Trade: {avg_return:.2f}%")
        print(f"Winning Trades: {wins} / {total_trades} ({win_rate:.2f}%)")
        print(f"Final Portfolio Value (All Tickers): ${combined_final_value:.2f}")
        print(f"Total Strategy P&L: ${combined_final_value - STARTING_CASH:.2f}")
    else:
        print("No trades were executed.")
