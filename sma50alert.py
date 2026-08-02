import yfinance as yf
import requests
import os
from datetime import datetime

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

with open("watchlist.txt", "r") as f:
    WATCHLIST = [line.strip() for line in f if line.strip()]

exit_stocks = []
scanned = 0

for symbol in WATCHLIST:
    try:
        df = yf.download(
            symbol,
            period="6mo",
            interval="1d",
            auto_adjust=True,
            progress=False
        )

        if len(df) < 50:
            continue

        scanned += 1

        close = float(df["Close"].iloc[-1])
        sma50 = float(df["Close"].rolling(50).mean().iloc[-1])
        diff = ((close - sma50) / sma50) * 100

        stock_info = (
            f"{symbol}\n"

            f"Close: {close:.2f}\n"

            f"SMA50: {sma50:.2f}\n"

            f"Diff: {diff:.2f}%"
        )

        if close < sma50:
            exit_stocks.append((diff, stock_info))

    except Exception as e:
        print(f"Error processing {symbol}: {e}")

exit_stocks.sort(key=lambda x: x[0])

message = (
    f"✅ SMA50 Scan Completed\n"

    f"Stocks Scanned: {scanned}\n"

    f"Exits: {len(exit_stocks)}\n"

    f"Date: {datetime.now().strftime('%Y-%m-%d')}"

)

if exit_stocks:
    message += "🚨 EXITS (Below SMA50)

"
    message += "

".join([item[1] for item in exit_stocks])
else:
    message += "🎉 No stocks are below SMA50 today."

requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
    data={
        "chat_id": CHAT_ID,
        "text": message
    }
)

print(message)
