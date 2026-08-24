import os

log = []

log.append("UPSTOX SCRIPT STARTED")

token = os.getenv("UPSTOX_ACCESS_TOKEN")
print("Token found:", bool(token))
if token:
    print("Token Length:", len(token))
if token:
    log.append("Access token found")
else:
    log.append("ERROR: Access token missing")
import json
import requests
import traceback
from datetime import datetime

ACCESS_TOKEN = "os.getenv(UPSTOX_ACCESS_TOKEN)"

HEADERS = {
    "Accept": "application/json",
    "Authorization": f"Bearer {ACCESS_TOKEN}"
}

BASE_URL = "https://api.upstox.com/v2"

errors = []


# -------------------------
# LOAD WATCHLIST
# -------------------------

def load_watchlist():
    try:
        with open("watchlist.txt", "r") as f:
            return [
                x.strip()
                for x in f.readlines()
                if x.strip()
            ]
    except Exception as e:
        errors.append(f"watchlist.txt error: {e}")
        return []


# -------------------------
# LOAD ISIN MAP
# -------------------------

def load_isin_map():
    try:
        with open("isin_mapping.json", "r") as f:
            return json.load(f)
    except Exception as e:
        errors.append(
            f"isin_mapping.json error: {e}"
        )
        return {}


# -------------------------
# Corporate Actions
# -------------------------

def get_corporate_actions(symbol, isin):

    try:

        url = (
            f"{BASE_URL}/fundamentals/"
            f"{isin}/corporate-actions"
        )

        r = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        r.raise_for_status()

        data = r.json()

        lines = []

        actions = data.get("data", [])

        if not actions:
            return [f"{symbol}: No actions"]

        for a in actions[:5]:

            name = a.get("name")

            expiry = a.get("expiry_date")

            amount = a.get("amount")

            lines.append(
                f"{symbol}: {name} "
                f"(Amount={amount}, "
                f"Date={expiry})"
            )

        return lines

    except Exception as e:

        errors.append(
            f"{symbol} Corporate Action Error: {e}"
        )

        return []


# -------------------------
# Shareholding
# -------------------------

def get_shareholding(symbol, isin):

    try:

        url = (
            f"{BASE_URL}/fundamentals/"
            f"{isin}/share-holdings"
        )

        r = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        if r.status_code != 200:
            raise Exception(
                f"HTTP {r.status_code}"
            )

        data = r.json()

        holdings = data.get("data", [])

        if not holdings:
            return [f"{symbol}: No shareholding data"]

        latest = holdings[0]

        return [
            (
                f"{symbol}: "
                f"Promoter={latest.get('promoters')}%, "
                f"FII={latest.get('fiis')}%, "
                f"DII={latest.get('diis')}%"
            )
        ]

    except Exception as e:

        errors.append(
            f"{symbol} Shareholding Error: {e}"
        )

        return []


# -------------------------
# Income Statements
# -------------------------

def get_financials(symbol, isin):

    try:

        url = (
            f"{BASE_URL}/fundamentals/"
            f"{isin}/income-statement"
        )

        r = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        if r.status_code != 200:
            raise Exception(
                f"HTTP {r.status_code}"
            )

        data = r.json()

        rows = data.get("data", [])

        if not rows:
            return [f"{symbol}: No results"]

        latest = rows[0]

        return [
            (
                f"{symbol}: "
                f"Revenue={latest.get('revenue')}, "
                f"PAT={latest.get('net_profit')}"
            )
        ]

    except Exception as e:

        errors.append(
            f"{symbol} Income Statement Error: {e}"
        )

        return []


# -------------------------
# Build Report
# -------------------------

def build_report():

    watchlist = load_watchlist()

    isin_map = load_isin_map()

    corporate_section = []
    shareholding_section = []
    financial_section = []

    for symbol in watchlist:

        if symbol not in isin_map:

            errors.append(
                f"Missing ISIN Mapping: {symbol}"
            )

            continue

        isin = isin_map[symbol]

        corporate_section.extend(
            get_corporate_actions(
                symbol,
                isin
            )
        )

        shareholding_section.extend(
            get_shareholding(
                symbol,
                isin
            )
        )

        financial_section.extend(
            get_financials(
                symbol,
                isin
            )
        )

    html = f"""
    <html>
    <body>

    <h2>
    Portfolio Intelligence
    </h2>

    <p>
    Generated:
    {datetime.now()}
    </p>

    <hr>

    <h3>
    Corporate Actions
    </h3>

    <pre>
    {"\n".join(corporate_section)}
    </pre>

    <hr>

    <h3>
    Shareholding
    </h3>

    <pre>
    {"\n".join(shareholding_section)}
    </pre>

    <hr>

    <h3>
    Quarterly Results
    </h3>

    <pre>
    {"\n".join(financial_section)}
    </pre>

    <hr>

    <h3>
    System Issues
    </h3>

    <pre>
    {"\n".join(errors) if errors else "None"}
    </pre>

    </body>
    </html>
    """

    return html


if __name__ == "__main__":

    report = build_report()

    with open(
        "portfolio_report.html",
        "w",
        encoding="utf-8"
    ) as f:
        f.write(report)
    print(report)
    print("Report Generated")
with open("upstox_report.txt","w") as f:
    f.write("\n".join(log))
