import os
import requests
import resend
from datetime import datetime, timezone


# ============================================================
# SETTINGS
# ============================================================

WALLET = os.environ["HYPERLIQUID_WALLET"].strip()

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
# CHECK WALLET
# ============================================================

print("=" * 60)
print("HYPERLIQUID DEBUG")
print("=" * 60)

print(f"Wallet being queried:")
print(WALLET)

print(f"Wallet length: {len(WALLET)}")

print()


# ============================================================
# GET ACCOUNT STATE
# ============================================================

account = hl_request({
    "type": "clearinghouseState",
    "user": WALLET
})


print("RAW ACCOUNT RESPONSE:")
print(account)
print()


# ============================================================
# ACCOUNT VALUE / EQUITY
# ============================================================

margin = account.get("marginSummary", {})

account_value = float(
    margin.get("accountValue", 0)
)

margin_used = float(
    margin.get("totalMarginUsed", 0)
)

position_value = float(
    margin.get("totalNtlPos", 0)
)

withdrawable = float(
    account.get("withdrawable", 0)
)


positions = account.get("assetPositions", [])


print("ACCOUNT VALUES")
print("-" * 60)

print(f"Account Value:   ${account_value:,.2f}")
print(f"Position Value:  ${position_value:,.2f}")
print(f"Margin Used:     ${margin_used:,.2f}")
print(f"Withdrawable:    ${withdrawable:,.2f}")

print()

print(f"Open positions returned: {len(positions)}")

for position in positions:

    print(position)

print()


# ============================================================
# GET FILLS
# ============================================================

fills = hl_request({
    "type": "userFills",
    "user": WALLET,
    "aggregateByTime": False
})


print("=" * 60)
print("FILL INFORMATION")
print("=" * 60)

print(f"Total fills returned: {len(fills)}")

print()


# ============================================================
# SHOW LATEST FILLS
# ============================================================

if fills:

    print("LATEST FILLS:")
    print("-" * 60)

    for fill in fills[:10]:

        fill_time = datetime.fromtimestamp(
            fill["time"] / 1000,
            timezone.utc
        )

        print(
            fill_time,
            fill.get("coin"),
            fill.get("side"),
            fill.get("sz"),
            "closedPnl=",
            fill.get("closedPnl"),
            "fee=",
            fill.get("fee")
        )

else:

    print("NO FILLS RETURNED")


print()


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


print("=" * 60)
print("TODAY")
print("=" * 60)

print(f"UTC date: {today}")
print(f"Today's fills: {len(today_fills)}")

print()


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


DEBUG
-----

Wallet:
{WALLET}

Total fills returned:
{len(fills)}

Today's fills:
{len(today_fills)}

Open positions:
{len(positions)}
"""


print(report)


# ============================================================
# SEND EMAIL
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
