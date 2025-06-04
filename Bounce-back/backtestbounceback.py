import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import matplotlib.pyplot as plt

# Load credentials
load_dotenv()
API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")
TICKERS = [ticker.strip() for ticker in os.getenv("TICKERS", "").split(",") if ticker.strip()]

data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# Parameters
STARTING_CASH = 1000
POSITION_SIZE = 900
DROP_PCT = 3.0
TAKE_PROFIT_PCT = 2.0
STOP_LOSS_PCT = -0.35
HOLD_HOURS_MAX = 72
DROP_LOOKBACK_BARS = 60

START_DATE = datetime(2025, 1, 1, tzinfo=pytz.UTC)
END_DATE = datetime(2025, 6, 1, tzinfo=pytz.UTC)

def fetch_minute_data(symbol, start, end):
    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
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
        current_price = now["open"]

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

        else:
            window = prices.iloc[i - DROP_LOOKBACK_BARS:i]
            max_close = window["close"].max()
            drop_pct = (current_price - max_close) / max_close * 100
            sma10 = prices["close"].rolling(10).mean().iloc[i-1]
            trend_ok = now["close"] > sma10

            if drop_pct <= -DROP_PCT and trend_ok:
                shares_to_buy = POSITION_SIZE / current_price
                if cash >= shares_to_buy * current_price:
                    cash -= shares_to_buy * current_price
                    position = {
                        "entry_time": now_time,
                        "entry_price": current_price,
                        "shares": shares_to_buy
                    }

    # Close any open position at the final price
    if position:
        final_price = prices.iloc[-1]["close"]
        shares = position["shares"]
        cash += shares * final_price
        trades.append({
            "buy_time": position["entry_time"],
            "buy_price": position["entry_price"],
            "sell_time": prices.iloc[-1].name,
            "sell_price": final_price,
            "return_pct": (final_price - position["entry_price"]) / position["entry_price"] * 100
        })

    return cash, trades

def plot_trades(prices, trades, ticker):
    plt.figure(figsize=(14, 6))
    plt.plot(prices.index, prices["close"], label="Price", alpha=0.8)

    for i, trade in enumerate(trades):
        plt.scatter(trade["buy_time"], trade["buy_price"], marker="^", color="green", label="Buy" if i == 0 else "", zorder=5)
        plt.scatter(trade["sell_time"], trade["sell_price"], marker="v", color="red", label="Sell" if i == 0 else "", zorder=5)

    # Compute additional info
    returns = [t["return_pct"] for t in trades]
    total_return = sum(returns)
    win_count = sum(r > 0 for r in returns)
    win_rate = (win_count / len(returns) * 100) if trades else 0
    avg_return = np.mean(returns) if trades else 0

    # Add dynamic subtitle text
    subtitle = (
        f"Total Trades: {len(trades)} | "
        f"Win Rate: {win_rate:.1f}% | "
        f"Avg Return: {avg_return:.2f}% | "
        f"Total Return: {total_return:.2f}%"
    )

    plt.title(f"{ticker} Backtest — Buy -{DROP_PCT}%, Sell +{TAKE_PROFIT_PCT}%\n{subtitle}", fontsize=13)
    plt.xlabel("Datetime")
    plt.ylabel("Price")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.show()



def main():
    all_trades = []
    combined_final_value = 0
    

    for TICKER in TICKERS:
        print(f"\n=== Running Backtest for {TICKER} ===")
        try:
            prices = fetch_minute_data(TICKER, START_DATE, END_DATE)
            if prices.empty:
                print(f"No data for {TICKER}, skipping.")
                continue

            cash, trades = run_backtest(prices)
            combined_final_value += cash
            all_trades.extend(trades)

            print(f"\n--- Backtest Result for {TICKER} ---")
            print(f"Final Portfolio Value: ${cash:.2f}")
            print(f"Total Trades: {len(trades)}\n")
            for trade in trades:
                print(f"{trade['buy_time']} BUY @ ${trade['buy_price']:.2f} → "
                      f"{trade['sell_time']} SELL @ ${trade['sell_price']:.2f} | "
                      f"Return: {trade['return_pct']:.2f}%")

            # plot_trades(prices, trades, TICKER)

        except Exception as e:
            print(f"Error while processing {TICKER}: {e}")

    print("\n=== TOTAL STRATEGY SUMMARY ===")
    total_trades = len(all_trades)
    duration_days = (END_DATE - START_DATE).days
    duration_months = duration_days / 30.0  # Approximate

    if total_trades > 0:
        returns = [t["return_pct"] for t in all_trades]
        avg_return = np.mean(returns)
        win_rate = sum(r > 0 for r in returns) / total_trades * 100
        sharpe = avg_return / np.std(returns) if np.std(returns) != 0 else 0

        starting_total = STARTING_CASH * len(TICKERS)
        total_return_pct = ((combined_final_value - starting_total) / starting_total) * 100

        print(f"Total Trades: {total_trades}")
        print(f"Average Return per Trade: {avg_return:.2f}%")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Sharpe Ratio: {sharpe:.2f}")
        print(f"Backtest Duration: {duration_days} days ({duration_months:.1f} months)")
        print(f"Total Return: {total_return_pct:.2f}%")
        print(f"Final Portfolio Value: ${combined_final_value:.2f}")
        print(f"Total Strategy P&L: ${combined_final_value - starting_total:.2f}")
    else:
        print("No trades were executed.")


if __name__ == "__main__":
    main()
