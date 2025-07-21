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

# Timezone setup
est = pytz.timezone("US/Eastern")

# Load API keys
load_dotenv()
API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")
TICKERS = [ticker.strip() for ticker in os.getenv("TICKERS", "").split(",") if ticker.strip()]

# Alpaca client
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# Strategy parameters
STARTING_CASH = 1000
POSITION_SIZE = 700
DROP_PCT = 5
TAKE_PROFIT_PCT = 12
STOP_LOSS_PCT = -5
TRAILING_STOP_LOSS_PCT = -5
HOLD_HOURS_MAX = 72
DROP_LOOKBACK_BARS = 50
COOLDOWN_HOURS = 4

START_DATE = datetime(2024, 7, 1, tzinfo=pytz.UTC)
END_DATE = datetime(2025, 7, 1, tzinfo=pytz.UTC)


def fetch_hourly_data(symbol, start, end):
    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Hour,
        start=start,
        end=end,
        feed="sip"
    )
    bars = data_client.get_stock_bars(request).df
    return bars.xs(symbol, level=0)


def fetch_5min_exit_data(ticker, start_time, hold_hours):
    end_time = start_time + timedelta(hours=hold_hours)
    request = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=TimeFrame.Minute,
        start=start_time,
        end=end_time,
        feed="sip"
    )
    bars = data_client.get_stock_bars(request).df
    return bars.xs(ticker, level=0) if not bars.empty else pd.DataFrame()


def run_backtest(ticker, prices):
    cash = STARTING_CASH
    position = None
    trades = []
    cooldown_end_time = None

    for i in range(DROP_LOOKBACK_BARS + 1, len(prices)):
        now = prices.iloc[i]
        now_time = now.name
        current_price = now["close"]

        if position:
            exit_data = fetch_5min_exit_data(ticker, position["entry_time"], HOLD_HOURS_MAX)

            for _, row in exit_data.iterrows():
                exit_time = row.name
                exit_price = row["close"]
                time_held = (exit_time - position["entry_time"]).total_seconds() / 3600
                max_price = max(position["max_price_since_entry"], exit_price)
                position["max_price_since_entry"] = max_price

                return_pct = (exit_price - position["entry_price"]) / position["entry_price"] * 100
                trailing_drop_pct = (exit_price - max_price) / max_price * 100

                if (return_pct >= TAKE_PROFIT_PCT or
                    return_pct <= STOP_LOSS_PCT or
                    trailing_drop_pct <= TRAILING_STOP_LOSS_PCT or
                    time_held >= HOLD_HOURS_MAX):

                    shares = position["shares"]
                    cash += shares * exit_price
                    trades.append({
                        "buy_time": position["entry_time"],
                        "buy_price": position["entry_price"],
                        "sell_time": exit_time,
                        "sell_price": exit_price,
                        "return_pct": return_pct
                    })
                    position = None

                    if return_pct <= STOP_LOSS_PCT:
                        cooldown_end_time = exit_time + timedelta(hours=COOLDOWN_HOURS)
                    break
            continue

        if cooldown_end_time and now_time < cooldown_end_time:
            continue

        window = prices.iloc[i - DROP_LOOKBACK_BARS - 1:i - 1]
        max_high = window["high"].max()
        drop_pct = (now["close"] - max_high) / max_high * 100
        sma20 = prices["close"].rolling(20).mean().iloc[i - 1]
        sma50 = prices["close"].rolling(50).mean().iloc[i - 1]
        trend_ok = now["close"] > sma20 and sma20 > sma50
        bounce_ok = now["close"] > prices.iloc[i - 1]["close"]

        if drop_pct <= -DROP_PCT and trend_ok and bounce_ok:
            shares_to_buy = POSITION_SIZE / current_price
            if cash >= shares_to_buy * current_price:
                cash -= shares_to_buy * current_price
                position = {
                    "entry_time": now_time,
                    "entry_price": current_price,
                    "shares": shares_to_buy,
                    "max_price_since_entry": current_price
                }

    return cash, trades


def main():
    all_trades = []
    combined_final_value = 0

    for TICKER in TICKERS:
        print(f"\n=== Running Backtest for {TICKER} ===")
        try:
            prices = fetch_hourly_data(TICKER, START_DATE, END_DATE)
            if prices.empty:
                print(f"No data for {TICKER}, skipping.")
                continue

            cash, trades = run_backtest(TICKER, prices)
            combined_final_value += cash
            all_trades.extend(trades)

            print(f"Final Portfolio Value: ${cash:.2f} | Trades: {len(trades)}")
            for trade in trades:
                print(f"BUY: {trade['buy_time']} @ {trade['buy_price']:.2f} → SELL: {trade['sell_time']} @ {trade['sell_price']:.2f} | Return: {trade['return_pct']:.2f}%")

        except Exception as e:
            print(f"Error while processing {TICKER}: {e}")

    print("\n=== STRATEGY SUMMARY ===")
    total_trades = len(all_trades)
    if total_trades > 0:
        returns = [t["return_pct"] for t in all_trades]
        avg_return = np.mean(returns)
        win_rate = sum(r > 0 for r in returns) / total_trades * 100
        sharpe = avg_return / np.std(returns) if np.std(returns) != 0 else 0
        starting_total = STARTING_CASH * len(TICKERS)
        total_return_pct = ((combined_final_value - starting_total) / starting_total) * 100

        print(f"Total Trades: {total_trades}")
        print(f"Avg Return: {avg_return:.2f}% | Win Rate: {win_rate:.2f}% | Sharpe: {sharpe:.2f}")
        print(f"Total Return: {total_return_pct:.2f}% | Final Portfolio: ${combined_final_value:.2f}")
    else:
        print("No trades executed.")


if __name__ == "__main__":
    main()