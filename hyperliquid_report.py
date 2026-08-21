import os
import requests
import resend
from datetime import datetime, timezone


# ============================================================
# SETTINGS
# ============================================================

WALLET = os.environ["HYPERLIQUID_WALLET"]

RESEND_API_KEY = os.environ["RESEND_API_KEY"]
EMAIL_FROM = os.environ["EMAIL_FROM"]

EMAIL_TO = [
    x.strip()
    for x in os.environ["EMAIL_TO"].split(",")
    if x.strip()
]


# ============================================================
# RESEND
# ============================================================

resend.api_key = RESEND_API_KEY


# ============================================================
# HYPERLIQUID API
# ============================================================

URL = "https://api.hyperliquid.xyz/info"


def hl_request(payload):

    response = requests.post(
        URL,
        json=payload,
        headers={
            "Content-Type": "application/json"
        },
        timeout=30
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# GET ACCOUNT VALUE / EQUITY
# ============================================================

account = hl_request({
    "type": "clearinghouseState",
    "user": WALLET
})


margin = account["marginSummary"]

account_value = float(
    margin["accountValue"]
)

margin_used = float(
    margin["totalMarginUsed"]
)

position_value = float(
    margin["totalNtlPos"]
)

withdrawable = float(
    account["withdrawable"]
)


# ============================================================
# GET FILLS
# ============================================================

fills = hl_request({
    "type": "userFills",
    "user": WALLET,
    "aggregateByTime": False
})


# ============================================================
# TODAY
# ============================================================

today = datetime.now(
    timezone.utc
).date()


today_fills = [
    x for x in fills
    if datetime.fromtimestamp(
        x["time"] / 1000,
        timezone.utc
    ).date() == today
]


# ============================================================
# P&L
# ============================================================

closed_pnl = sum(
    float(x.get("closedPnl", 0))
    for x in today_fills
)


fees = sum(
    abs(float(x.get("fee", 0)))
    for x in today_fills
)


net_pnl = closed_pnl - fees


# ============================================================
# REPORT
# ============================================================

report = f"""
HYPERLIQUID DAILY REPORT
========================

Date: {today}

ACCOUNT
-------

Account Value / Equity: ${account_value:,.2f}
Position Value:         ${position_value:,.2f}
Margin Used:            ${margin_used:,.2f}
Withdrawable:           ${withdrawable:,.2f}


TODAY'S TRADING
---------------

Trades/Fills:           {len(today_fills)}
Closed P&L:             ${closed_pnl:,.2f}
Trading Fees:           ${fees:,.2f}
NET P&L:                ${net_pnl:,.2f}
"""


print(report)


# ============================================================
# SEND EMAIL USING RESEND
# ============================================================

subject = f"Hyperliquid Daily Report - {today}"


params = {
    "from": EMAIL_FROM,
    "to": EMAIL_TO,
    "subject": subject,
    "text": report
}


try:

    email = resend.Emails.send(params)

    print("Email sent successfully.")
    print(email)

except Exception as e:

    print("Failed to send email.")
    print(e)

    raise
