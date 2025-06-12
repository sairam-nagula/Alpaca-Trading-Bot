import os
from dotenv import load_dotenv
from alpaca.data.live import StockDataStream
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest

# Load credentials
load_dotenv()
API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")

# Create the stream client (for real-time bars)
stream = StockDataStream(API_KEY, SECRET_KEY)

# Create the historical client (for latest quote & trade info)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# Define the handler for incoming bar data
async def handle_bar(bar):
    print(f"\n[BAR] [{bar.timestamp}] {bar.symbol} | O: {bar.open} H: {bar.high} L: {bar.low} C: {bar.close} V: {bar.volume}")

    # Fetch latest quote
    quote_req = StockLatestQuoteRequest(symbol_or_symbols=bar.symbol)
    quote = data_client.get_stock_latest_quote(quote_req)
    quote_data = quote[bar.symbol]
    print(f"[QUOTE] Ask: {quote_data.ask_price}, Bid: {quote_data.bid_price}")

    # Fetch latest trade
    trade_req = StockLatestTradeRequest(symbol_or_symbols=bar.symbol)
    trade = data_client.get_stock_latest_trade(trade_req)
    trade_data = trade[bar.symbol]
    print(f"[TRADE] Price: {trade_data.price}, Size: {trade_data.size}, Time: {trade_data.timestamp}")

# Subscribe to bars

stream.subscribe_bars(handle_bar, "AAPL")

# Start the stream
stream.run()