import os
import yfinance as yf
import pandas as pd
import requests

# =====================
# CONFIGURATION
# =====================

BOT_TOKEN = "os.environ["BOT_TOKEN"]
CHAT_ID = "os.environ["CHAT_ID"]

WATCHLIST = [
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "SBIN.NS"
]

# =====================
# ANALYSIS
# =====================

above_sma = []
exit_stocks = []

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
            exit_stocks.append(stock_info)
        else:
            above_sma.append(stock_info)

    except Exception as e:
        print(f"Error processing {symbol}: {e}")

# =====================
# MESSAGE
# =====================

message = "📊 SMA50 STATUS REPORT\n\n"

if exit_stocks:
    message += "🚨 EXITS (Below SMA50)\n\n"
    message += "\n\n".join(exit_stocks)
    message += "\n\n"

if above_sma:
    message += "✅ ABOVE SMA50\n\n"
    message += "\n\n".join(above_sma)

# =====================
# TELEGRAM
# =====================

requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
    data={
        "chat_id": CHAT_ID,
        "text": message
    }
)

print(message)
