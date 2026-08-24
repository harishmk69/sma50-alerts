import os
import json
import urllib.parse
from datetime import datetime
import requests
import pyotp

BASE_URL = "https://api.upstox.com/v2"
errors = []
log = []

# -------------------------
# AUTOMATED TOTP LOGIN
# -------------------------
def get_daily_access_token():
    """Automates Upstox login flow via TOTP to fetch a fresh daily access token."""
    api_key = os.getenv("UPSTOX_API_KEY")
    api_secret = os.getenv("UPSTOX_API_SECRET")
    rurl = os.getenv("UPSTOX_RURL")
    mobile = os.getenv("UPSTOX_MOBILE")
    pin = os.getenv("UPSTOX_PIN")
    totp_key = os.getenv("UPSTOX_TOTP_KEY")

    # Fallback to manual token if provided directly
    manual_token = os.getenv("UPSTOX_ACCESS_TOKEN")
    if manual_token and not (api_key and totp_key):
        log.append("Using manual UPSTOX_ACCESS_TOKEN from environment.")
        return manual_token

    if not all([api_key, api_secret, rurl, mobile, pin, totp_key]):
        missing = [
            k for k, v in {
                "UPSTOX_API_KEY": api_key,
                "UPSTOX_API_SECRET": api_secret,
                "UPSTOX_RURL": rurl,
                "UPSTOX_MOBILE": mobile,
                "UPSTOX_PIN": pin,
                "UPSTOX_TOTP_KEY": totp_key
            }.items() if not v
        ]
        errors.append(f"Missing required secrets for TOTP login: {', '.join(missing)}")
        return None

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json"
    })

    try:
        # Step 1: Initiate Auth
        auth_url = (
            f"{BASE_URL}/login/authorization/dialog"
            f"?response_type=code&client_id={api_key.strip()}&redirect_uri={urllib.parse.quote(rurl.strip(), safe='')}"
        )
        res1 = session.get(auth_url, timeout=15)
        if res1.status_code >= 400:
            errors.append(f"Step 1 (Dialog) Error {res1.status_code}: {res1.text}")
            return None

        # Step 2: Clean TOTP key and submit OTP
        clean_totp_key = "".join(totp_key.split()).replace("-", "").upper()
        if "secret=" in clean_totp_key:
            clean_totp_key = clean_totp_key.split("secret=")[1].split("&")[0]

        totp = pyotp.TOTP(clean_totp_key)
        otp = totp.now()

        otp_payload = {"mobileNumber": mobile.strip(), "otp": str(otp)}
        otp_res = session.post(f"{BASE_URL}/login/authorization/token", json=otp_payload, timeout=15)
        if otp_res.status_code >= 400:
            errors.append(f"Step 2 (OTP) Error {otp_res.status_code}: {otp_res.text}")
            return None

        # Step 3: Submit 6-digit PIN
        pin_payload = {"pin": str(pin).strip()}
        pin_res = session.post(f"{BASE_URL}/login/authorization/pin", json=pin_payload, timeout=15)
        if pin_res.status_code >= 400:
            errors.append(f"Step 3 (PIN) Error {pin_res.status_code}: {pin_res.text}")
            return None

        # Extract redirect location with auth code
        redirect_url = pin_res.headers.get("Location") or pin_res.json().get("data", {}).get("redirect_url")
        if not redirect_url:
            errors.append(f"Redirect URL extraction failed. Response: {pin_res.text}")
            return None

        parsed_url = urllib.parse.urlparse(redirect_url)
        auth_code = urllib.parse.parse_qs(parsed_url.query).get("code", [None])[0]
        if not auth_code:
            errors.append(f"Auth code not found in URL: {redirect_url}")
            return None

        # Step 4: Exchange Auth Code for Access Token
        token_url = f"{BASE_URL}/login/authorization/token"
        token_payload = {
            "code": auth_code,
            "client_id": api_key.strip(),
            "client_secret": api_secret.strip(),
            "redirect_uri": rurl.strip(),
            "grant_type": "authorization_code",
        }
        token_headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        token_res = requests.post(token_url, data=token_payload, headers=token_headers, timeout=15)
        if token_res.status_code >= 400:
            errors.append(f"Step 4 (Token Exchange) Error {token_res.status_code}: {token_res.text}")
            return None

        token_data = token_res.json()
        return token_data.get("access_token")

    except Exception as e:
        errors.append(f"TOTP Login Exception: {e}")
        return None


# -------------------------
# INITIALIZE ACCESS TOKEN
# -------------------------
ACCESS_TOKEN = get_daily_access_token()

if ACCESS_TOKEN:
    log.append("Access token generated/found successfully.")
else:
    log.append("ERROR: Failed to obtain valid access token.")

HEADERS = {
    "Accept": "application/json",
    "Authorization": f"Bearer {ACCESS_TOKEN}" if ACCESS_TOKEN else "",
}


# -------------------------
# LOAD WATCHLIST & ISIN MAP
# -------------------------
def load_watchlist():
    try:
        with open("watchlist.txt", "r") as f:
            return [x.strip() for x in f.readlines() if x.strip()]
    except Exception as e:
        errors.append(f"watchlist.txt error: {e}")
        return []

def load_isin_map():
    try:
        with open("isin_mapping.json", "r") as f:
            return json.load(f)
    except Exception as e:
        errors.append(f"isin_mapping.json error: {e}")
        return {}


# -------------------------
# FUNDAMENTALS API CALLS
# -------------------------
def get_corporate_actions(symbol, isin):
    if not ACCESS_TOKEN:
        return [f"{symbol}: Skipped (No Token)"]
    try:
        url = f"{BASE_URL}/fundamentals/{isin}/corporate-actions"
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()

        actions = r.json().get("data", [])
        if not actions:
            return [f"{symbol}: No actions"]

        lines = []
        for a in actions[:5]:
            name = a.get("name")
            expiry = a.get("expiry_date")
            amount = a.get("amount")
            lines.append(f"{symbol}: {name} (Amount={amount}, Date={expiry})")
        return lines
    except Exception as e:
        errors.append(f"{symbol} Corporate Action Error: {e}")
        return []

def get_shareholding(symbol, isin):
    if not ACCESS_TOKEN:
        return [f"{symbol}: Skipped (No Token)"]
    try:
        url = f"{BASE_URL}/fundamentals/{isin}/share-holdings"
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            raise Exception(f"HTTP {r.status_code}")

        holdings = r.json().get("data", [])
        if not holdings:
            return [f"{symbol}: No shareholding data"]

        latest = holdings[0]
        return [
            f"{symbol}: Promoter={latest.get('promoters')}%, FII={latest.get('fiis')}%, DII={latest.get('diis')}%"
        ]
    except Exception as e:
        errors.append(f"{symbol} Shareholding Error: {e}")
        return []

def get_financials(symbol, isin):
    if not ACCESS_TOKEN:
        return [f"{symbol}: Skipped (No Token)"]
    try:
        url = f"{BASE_URL}/fundamentals/{isin}/income-statement"
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            raise Exception(f"HTTP {r.status_code}")

        rows = r.json().get("data", [])
        if not rows:
            return [f"{symbol}: No results"]

        latest = rows[0]
        return [
            f"{symbol}: Revenue={latest.get('revenue')}, PAT={latest.get('net_profit')}"
        ]
    except Exception as e:
        errors.append(f"{symbol} Income Statement Error: {e}")
        return []


# -------------------------
# BUILD REPORT
# -------------------------
def build_report():
    watchlist = load_watchlist()
    isin_map = load_isin_map()

    corporate_section = []
    shareholding_section = []
    financial_section = []

    for symbol in watchlist:
        if symbol not in isin_map:
            errors.append(f"Missing ISIN Mapping: {symbol}")
            continue

        isin = isin_map[symbol]
        corporate_section.extend(get_corporate_actions(symbol, isin))
        shareholding_section.extend(get_shareholding(symbol, isin))
        financial_section.extend(get_financials(symbol, isin))

    html = f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.5;">
    <h3>📊 Upstox Portfolio Fundamentals</h3>
    <p><b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    
    <hr>
    <h4>Corporate Actions</h4>
    <pre style="background: #f8f9fa; padding: 10px; border-radius: 4px;">{chr(10).join(corporate_section) if corporate_section else 'None'}</pre>
    
    <hr>
    <h4>Shareholding Pattern</h4>
    <pre style="background: #f8f9fa; padding: 10px; border-radius: 4px;">{chr(10).join(shareholding_section) if shareholding_section else 'None'}</pre>
    
    <hr>
    <h4>Quarterly Results</h4>
    <pre style="background: #f8f9fa; padding: 10px; border-radius: 4px;">{chr(10).join(financial_section) if financial_section else 'None'}</pre>
    
    <hr>
    <h4 style="color: {'#d93025' if errors else '#188038'};">System Issues</h4>
    <pre style="background: #f8f9fa; padding: 10px; border-radius: 4px;">{chr(10).join(errors) if errors else 'None'}</pre>
    </div>
    """
    return html


if __name__ == "__main__":
    report = build_report()
    with open("portfolio_report.html", "w", encoding="utf-8") as f:
        f.write(report)
    with open("upstox_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(log))
    print("Upstox Report Generated Successfully")
