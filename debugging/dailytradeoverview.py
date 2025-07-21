import os
import pandas as pd
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

# === CONFIGURATION ===
load_dotenv()
API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")
trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)

# === SET TARGET DATE HERE ===
TARGET_DATE = '2025-07-03'  

# === FETCH TRADES FOR SPECIFIC DATE ===
def fetch_trades_by_date(target_date_str):
    eastern = pytz.timezone('US/Eastern')
    try:
        target_date = datetime.strptime(target_date_str, '%Y-%m-%d')
    except ValueError:
        print("Invalid date format. Please use YYYY-MM-DD.")
        return pd.DataFrame()

    start_time = eastern.localize(datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0)).astimezone(pytz.UTC)
    end_time = start_time + timedelta(days=1)

    order_filter = GetOrdersRequest(
        status=QueryOrderStatus.CLOSED,
        after=start_time,
        until=end_time
    )

    all_orders = trading_client.get_orders(order_filter)
    trades = []

    for order in all_orders:
        if order.filled_at is not None:
            trades.append({
                "symbol": order.symbol,
                "side": order.side,
                "qty": float(order.filled_qty),
                "price": float(order.filled_avg_price),
                "time": order.filled_at.astimezone(eastern).strftime('%Y-%m-%d %H:%M:%S')
            })

    return pd.DataFrame(trades)

# === ANALYZE TRADES ===
def analyze_trades(trades_df, target_date_str):
    if trades_df.empty:
        print(f"No trades found for {target_date_str}.")
        return

    summary = []

    for symbol, group in trades_df.groupby("symbol"):
        buys = group[group["side"] == "buy"]
        sells = group[group["side"] == "sell"]

        total_bought = buys["qty"].sum()
        total_sold = sells["qty"].sum()
        avg_buy_price = buys["price"].mean() if not buys.empty else 0
        avg_sell_price = sells["price"].mean() if not sells.empty else 0

        gross_buy_value = (buys["qty"] * buys["price"]).sum()
        gross_sell_value = (sells["qty"] * sells["price"]).sum()

        net_profit = gross_sell_value - gross_buy_value
        net_pct = (net_profit / gross_buy_value * 100) if gross_buy_value > 0 else 0

        buy_count = len(buys)
        sell_count = len(sells)

        wins = sells[sells["price"] > avg_buy_price]
        win_rate = (len(wins) / sell_count * 100) if sell_count > 0 else 0

        summary.append({
            "Symbol": symbol,
            "Total Buys": total_bought,
            "Buy Count": buy_count,
            "Avg Buy Price": avg_buy_price,
            "Total Sells": total_sold,
            "Sell Count": sell_count,
            "Avg Sell Price": avg_sell_price,
            "Gross Buy Value": gross_buy_value,
            "Gross Sell Value": gross_sell_value,
            "Net P/L ($)": net_profit,
            "Net % Return": net_pct,
            "Win Rate (%)": win_rate,
            "Trades Count": buy_count + sell_count
        })

    summary_df = pd.DataFrame(summary)
    pd.set_option('display.max_columns', None)

    print(f"\n=== Trade Summary for {target_date_str} ===")
    print(summary_df.to_string(index=False))

def main():
    trades_df = fetch_trades_by_date(TARGET_DATE)
    analyze_trades(trades_df, TARGET_DATE)

if __name__ == "__main__":
    main()