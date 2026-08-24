import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
import yfinance as yf

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

        close = float(df["Close"].iloc[-1].item())
        sma50 = float(df["Close"].rolling(50).mean().iloc[-1].item())
        diff = ((close - sma50) / sma50) * 100

        stock_info = (
            f"<b>{symbol}</b><br>"
            f"Close: {close:.2f} | SMA50: {sma50:.2f} | Diff: <span style='color: red;'>{diff:.2f}%</span>"
        )

        if close < sma50:
            exit_stocks.append((diff, stock_info))

    except Exception as e:
        print(f"Error processing {symbol}: {e}")

# Sort worst performers first
exit_stocks.sort(key=lambda x: x[0])

# =====================
# READ UPSTOX REPORT
# =====================

upstox_section = ""
if os.path.exists("portfolio_report.html"):
    try:
        with open("portfolio_report.html", "r", encoding="utf-8") as f:
            upstox_section = f.read()
    except Exception as e:
        upstox_section = f"<p>Error reading Upstox report: {e}</p>"
else:
    upstox_section = "<p><i>Upstox report not found. Check workflow run logs.</i></p>"

# =====================
# BUILD HTML EMAIL BODY
# =====================

if exit_stocks:
    exit_list_html = "<br><hr style='border-top: 1px dashed #ccc;'><br>".join(
        [item[1] for item in exit_stocks]
    )
    exits_content = f"<h3>🚨 EXITS (Below SMA50)</h3><div>{exit_list_html}</div>"
else:
    exits_content = "<p>🎉 <b>No stocks are below SMA50 today.</b></p>"

html_body = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 700px; margin: auto;">

    <div style="background-color: #f4f6f9; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
        <h2 style="margin-top: 0; color: #1a73e8;">✅ Daily Market & Portfolio Report</h2>
        <p style="margin: 0;"><b>Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p style="margin: 0;"><b>Stocks Scanned:</b> {scanned} | <b>Exits:</b> {len(exit_stocks)}</p>
    </div>

    <!-- SMA50 SECTION -->
    <div style="padding: 10px 0;">
        {exits_content}
    </div>

    <br>
    <hr style="border: 0; border-top: 2px solid #e0e0e0;">
    <br>

    <!-- UPSTOX FUNDAMENTALS SECTION -->
    <div>
        {upstox_section}
    </div>

</body>
</html>
"""

# =====================
# SEND EMAIL
# =====================

subject = f"Market Alert: SMA50 & Portfolio - {datetime.now().strftime('%Y-%m-%d')}"

# Note the subtype "html"
email = MIMEText(html_body, "html")
email["Subject"] = subject
email["From"] = EMAIL_ADDRESS
email["To"] = EMAIL_ADDRESS

try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(email)
    print("Combined Email sent successfully!")
except Exception as e:
    print(f"Failed to send email: {e}")
