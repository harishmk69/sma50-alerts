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
# LOAD WATCHLIST
# =====================
with open("watchlist.txt", "r") as f:
    WATCHLIST = [line.strip() for line in f if line.strip()]

# =====================
# SCAN & FETCH DATA
# =====================
exit_stocks = []
fundamentals_data = []
scanned = 0

for symbol in WATCHLIST:
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="6mo", interval="1d", auto_adjust=True)

        if len(df) < 50:
            continue

        scanned += 1

        # 1. Technical SMA50 Check
        close = float(df["Close"].iloc[-1])
        sma50 = float(df["Close"].rolling(50).mean().iloc[-1])
        diff = ((close - sma50) / sma50) * 100

        stock_info = (
            f"<b>{symbol}</b><br>"
            f"Close: ₹{close:.2f} | SMA50: ₹{sma50:.2f} | Diff: <span style='color: red;'>{diff:.2f}%</span>"
        )

        if close < sma50:
            exit_stocks.append((diff, stock_info))

        # 2. Corporate Actions (Recent dividends/splits)
        actions = ticker.actions.tail(2)
        action_summary = "None"
        if not actions.empty:
            action_lines = []
            for date, row in actions.iterrows():
                date_str = date.strftime('%Y-%m-%d')
                if row.get('Dividends', 0) > 0:
                    action_lines.append(f"Div: ₹{row['Dividends']:.2f} ({date_str})")
                if row.get('Stock Splits', 0) > 0:
                    action_lines.append(f"Split: {row['Stock Splits']} ({date_str})")
            if action_lines:
                action_summary = ", ".join(action_lines)

        # 3. Quarterly Results (Revenue & Net Income/PAT)
        q_inc = ticker.quarterly_income_stmt
        fin_summary = "N/A"
        if not q_inc.empty:
            latest_q_date = q_inc.columns[0].strftime('%b %Y')
            rev = q_inc.loc["Total Revenue"].iloc[0] if "Total Revenue" in q_inc.index else None
            pat = q_inc.loc["Net Income"].iloc[0] if "Net Income" in q_inc.index else None

            rev_str = f"₹{rev/1e7:.2f} Cr" if rev and rev > 0 else "N/A"
            pat_str = f"₹{pat/1e7:.2f} Cr" if pat else "N/A"
            fin_summary = f"{latest_q_date} -> Rev: {rev_str}, PAT: {pat_str}"

        fundamentals_data.append(
            f"<b>{symbol}</b><br>"
            f"• <b>Quarterly:</b> {fin_summary}<br>"
            f"• <b>Actions:</b> {action_summary}"
        )

    except Exception as e:
        print(f"Error processing {symbol}: {e}")

exit_stocks.sort(key=lambda x: x[0])

# =====================
# BUILD HTML EMAIL
# =====================
if exit_stocks:
    exit_list_html = "<br><hr style='border-top: 1px dashed #ccc;'><br>".join([item[1] for item in exit_stocks])
    exits_content = f"<h3 style='color: #d93025;'>🚨 EXITS (Below SMA50)</h3><div>{exit_list_html}</div>"
else:
    exits_content = "<p>🎉 <b>No stocks are below SMA50 today.</b></p>"

fundamentals_html = "<br><hr style='border-top: 1px dashed #eee;'><br>".join(fundamentals_data)

html_body = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 650px; margin: auto; padding: 15px;">
    <div style="background-color: #f4f6f9; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
        <h2 style="margin-top: 0; color: #1a73e8;">📈 Daily SMA50 & Fundamentals Alert</h2>
        <p style="margin: 0;"><b>Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p style="margin: 0;"><b>Stocks Scanned:</b> {scanned} | <b>SMA50 Exits:</b> {len(exit_stocks)}</p>
    </div>

    <div>{exits_content}</div>

    <br><hr style="border: 0; border-top: 2px solid #e0e0e0;"><br>

    <h3>📊 Fundamentals & Corporate Actions</h3>
    <div style="background: #fafafa; padding: 15px; border-radius: 6px; border: 1px solid #e0e0e0;">
        {fundamentals_html if fundamentals_html else 'No data found'}
    </div>
</body>
</html>
"""

# =====================
# SEND EMAIL
# =====================
subject = f"Market Alert: SMA50 & Fundamentals - {datetime.now().strftime('%Y-%m-%d')}"
email = MIMEText(html_body, "html")
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
