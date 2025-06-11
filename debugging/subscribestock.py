import os
from dotenv import load_dotenv
from alpaca.data.live import StockDataStream

# Load credentials
load_dotenv()
API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")

# Create the stream client
stream = StockDataStream(API_KEY, SECRET_KEY)

# Define the handler
async def handle_bar(bar):
    print(f"[{bar.timestamp}] {bar.symbol} | O: {bar.open} H: {bar.high} L: {bar.low} C: {bar.close} V: {bar.volume}")

# Subscribe to bars
stream.subscribe_bars(handle_bar, "AAPL")  # You can pass multiple tickers like: ["AAPL", "MSFT"]

# Start the stream
stream.run()
