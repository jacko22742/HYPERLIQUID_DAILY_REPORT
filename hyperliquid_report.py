import os
import requests
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone


# ============================================================
# SETTINGS
# ============================================================

WALLET = os.environ["HYPERLIQUID_WALLET"]

EMAIL_USERNAME = os.environ["EMAIL_USERNAME"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]

EMAIL_TO = [
    x.strip()
    for x in os.environ["EMAIL_TO"].split(",")
]


# ============================================================
# HYPERLIQUID
# ============================================================

url = "https://api.hyperliquid.xyz/info"


response = requests.post(
    url,
    json={
        "type": "userFills",
        "user": WALLET,
        "aggregateByTime": False
    },
    timeout=30
)

response.raise_for_status()

fills = response.json()


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

Date: {today}

Trades/Fills: {len(today_fills)}

Closed P&L: ${closed_pnl:,.2f}

Trading Fees: ${fees:,.2f}

NET P&L: ${net_pnl:,.2f}
"""


print(report)


# ============================================================
# SEND EMAIL
# ============================================================

message = MIMEText(
    report,
    "plain"
)

message["Subject"] = (
    f"Hyperliquid Daily P&L - {today}"
)

message["From"] = EMAIL_USERNAME

message["To"] = ", ".join(
    EMAIL_TO
)


with smtplib.SMTP(
    "smtp.gmail.com",
    587
) as server:

    server.starttls()

    server.login(
        EMAIL_USERNAME,
        EMAIL_PASSWORD
    )

    server.sendmail(
        EMAIL_USERNAME,
        EMAIL_TO,
        message.as_string()
    )


print("Email sent successfully.")
