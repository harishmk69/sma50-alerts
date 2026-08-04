import yfinance as yf
import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText

# =====================
# CONFIGURATION
# =====================

EMAIL_ADDRESS = os.environ["EMAIL_ADDRESS"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]

# =====================
# WATCHLIST
# =====================

with open("watchlist.txt", "r") as f:
    WATCHLIST = [line.strip() for line in f if line.strip()]

# =====================
# ANALYSIS
# =====================

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

        # .item() prevents 'float() argument must be a string or a real number, not Series'
        close = float(df["Close"].iloc[-1].item())
        sma50 = float(df["Close"].rolling(50).mean().iloc[-1].item())

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

# Sort worst performers first
exit_stocks.sort(key=lambda x: x[0])

# =====================
# MESSAGE
# =====================

message = (
    f"✅ SMA50 Scan Completed\n\n"
    f"Stocks Scanned: {scanned}\n"
    f"Exits: {len(exit_stocks)}\n"
    f"Date: {datetime.now().strftime('%Y-%m-%d')}\n\n"
)

if exit_stocks:
    message += "🚨 EXITS (Below SMA50)\n\n"
    message += "\n----------------------------------------\n".join(
        [item[1] for item in exit_stocks]
    )
else:
    message += "🎉 No stocks are below SMA50 today."

# =====================
# EMAIL
# =====================

subject = f"SMA50 Scan - {datetime.now().strftime('%Y-%m-%d')}"

email = MIMEText(message)
email["Subject"] = subject
email["From"] = EMAIL_ADDRESS
email["To"] = EMAIL_ADDRESS

try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(email)
    print("Email sent successfully!")
except Exception as e:
    print(f"Failed to send email: {e}")
