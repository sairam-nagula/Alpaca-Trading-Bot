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

# === TIME CONFIG ===
eastern = pytz.timezone('US/Eastern')
now = datetime.now(eastern)
start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(pytz.UTC)

# === FETCH TODAY'S TRADES ===
def fetch_todays_trades():
    order_filter = GetOrdersRequest(
        status=QueryOrderStatus.CLOSED,
        after=start_of_day
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
                "time": order.filled_at
            })

    return pd.DataFrame(trades)

# === ANALYZE TRADES ===
def analyze_trades(trades_df):
    if trades_df.empty:
        print("No trades found for today.")
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

    print("\n=== Today's Trade Summary ===")
    print(summary_df.to_string(index=False))

def main():
    trades_df = fetch_todays_trades()
    analyze_trades(trades_df)

if __name__ == "__main__":
    main()
