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
# ACCOUNT STATE
# ============================================================

account = hl_request({
    "type": "clearinghouseState",
    "user": WALLET
})


margin = account.get("marginSummary", {})

cross_margin = account.get(
    "crossMarginSummary",
    {}
)


# ============================================================
# ACCOUNT VALUES
# ============================================================

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


# ============================================================
# POSITIONS
# ============================================================

positions = account.get(
    "assetPositions",
    []
)


# ============================================================
# FILLS
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
    x
    for x in fills
    if datetime.fromtimestamp(
        x["time"] / 1000,
        timezone.utc
    ).date() == today
]


# ============================================================
# REALISED P&L
# ============================================================

realised_pnl = sum(
    float(x.get("closedPnl", 0))
    for x in today_fills
)


# ============================================================
# FEES
# ============================================================

fees = sum(
    abs(float(x.get("fee", 0)))
    for x in today_fills
)


# ============================================================
# NET P&L
# ============================================================

net_pnl = realised_pnl - fees


# ============================================================
# TRADE BREAKDOWN
# ============================================================

long_entries = 0
short_entries = 0

long_reductions = 0
short_reductions = 0


for fill in today_fills:

    side = str(
        fill.get("side", "")
    ).upper()

    closed_pnl = float(
        fill.get("closedPnl", 0)
    )

    # Hyperliquid sides:
    #
    # B = Buy
    # A = Sell
    #
    # A fill with non-zero closedPnl
    # generally represents reduction/closure
    #
    # B fill with non-zero closedPnl
    # generally represents reduction/closure


    if side in ("B", "BUY"):

        if abs(closed_pnl) > 0:
            long_reductions += 1
        else:
            long_entries += 1


    elif side in ("A", "SELL"):

        if abs(closed_pnl) > 0:
            short_reductions += 1
        else:
            short_entries += 1


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

Fills:                  {len(today_fills)}

Long Entries:           {long_entries}
Short Entries:          {short_entries}

Long Reductions:        {long_reductions}
Short Reductions:       {short_reductions}


P&L
---

Realised P&L:           ${realised_pnl:,.2f}
Trading Fees:           ${fees:,.2f}

NET P&L:                ${net_pnl:,.2f}
"""


print(report)


# ============================================================
# SEND EMAIL
# ============================================================

subject = (
    f"Hyperliquid Daily Report - {today}"
)


params = {
    "from": EMAIL_FROM,
    "to": EMAIL_TO,
    "subject": subject,
    "text": report
}


try:

    email = resend.Emails.send(
        params
    )

    print(
        "Email sent successfully."
    )

except Exception as e:

    print(
        "Failed to send email."
    )

    print(e)

    raise
