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
# DEBUG - WALLET
# ============================================================

print("=" * 70)
print("HYPERLIQUID DAILY REPORT")
print("=" * 70)

print(f"Wallet length: {len(WALLET)}")
print(f"Wallet starts with: {WALLET[:6]}")
print(f"Wallet ends with: {WALLET[-6:]}")
print()


# ============================================================
# PERPETUAL CLEARINGHOUSE STATE
# ============================================================

account = hl_request({
    "type": "clearinghouseState",
    "user": WALLET
})


print("=" * 70)
print("PERPETUAL ACCOUNT STATE")
print("=" * 70)

print(account)
print()


# ============================================================
# ACCOUNT VALUES
# ============================================================

margin = account.get(
    "marginSummary",
    {}
)

cross_margin = account.get(
    "crossMarginSummary",
    {}
)


perp_equity = float(
    margin.get("accountValue", 0)
)


position_value = float(
    margin.get("totalNtlPos", 0)
)


margin_used = float(
    margin.get("totalMarginUsed", 0)
)


withdrawable = float(
    account.get("withdrawable", 0)
)


positions = account.get(
    "assetPositions",
    []
)


# ============================================================
# SPOT CLEARINGHOUSE STATE
# ============================================================

spot_account = hl_request({
    "type": "spotClearinghouseState",
    "user": WALLET
})


print("=" * 70)
print("SPOT ACCOUNT STATE")
print("=" * 70)

print(spot_account)
print()


# ============================================================
# SPOT BALANCES
# ============================================================

spot_balances = spot_account.get(
    "balances",
    []
)


usdc_balance = 0.0


for balance in spot_balances:

    coin = balance.get(
        "coin",
        ""
    )

    if coin.upper() == "USDC":

        usdc_balance = float(
            balance.get(
                "total",
                0
            )
        )

        break


# ============================================================
# PRINT ACCOUNT VALUES
# ============================================================

print("=" * 70)
print("ACCOUNT VALUES")
print("=" * 70)

print(
    f"Perp Equity:       ${perp_equity:,.2f}"
)

print(
    f"USDC Balance:      ${usdc_balance:,.2f}"
)

print(
    f"Position Value:    ${position_value:,.2f}"
)

print(
    f"Margin Used:       ${margin_used:,.2f}"
)

print(
    f"Withdrawable:      ${withdrawable:,.2f}"
)

print(
    f"Open Positions:    {len(positions)}"
)

print()


# ============================================================
# OPEN POSITIONS
# ============================================================

if positions:

    print("=" * 70)
    print("OPEN POSITIONS")
    print("=" * 70)

    for position in positions:

        print(position)

    print()

else:

    print("No open positions returned.")
    print()


# ============================================================
# GET FILLS
# ============================================================

fills = hl_request({
    "type": "userFills",
    "user": WALLET,
    "aggregateByTime": False
})


print("=" * 70)
print("FILLS")
print("=" * 70)

print(
    f"Total fills returned: {len(fills)}"
)

print()


# ============================================================
# SHOW RECENT FILLS IN GITHUB LOG
# ============================================================

if fills:

    print("LATEST FILLS")
    print("-" * 70)

    for fill in fills[:10]:

        fill_time = datetime.fromtimestamp(
            fill["time"] / 1000,
            timezone.utc
        )

        print(
            f"{fill_time} | "
            f"{fill.get('coin')} | "
            f"side={fill.get('side')} | "
            f"dir={fill.get('dir')} | "
            f"sz={fill.get('sz')} | "
            f"px={fill.get('px')} | "
            f"closedPnl={fill.get('closedPnl')} | "
            f"fee={fill.get('fee')}"
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
    x
    for x in fills
    if datetime.fromtimestamp(
        x["time"] / 1000,
        timezone.utc
    ).date() == today
]


print("=" * 70)
print("TODAY")
print("=" * 70)

print(
    f"UTC date:        {today}"
)

print(
    f"Today's fills:   {len(today_fills)}"
)

print()


# ============================================================
# TODAY'S FILLS
# ============================================================

if today_fills:

    print("TODAY'S FILLS")
    print("-" * 70)

    for fill in today_fills:

        fill_time = datetime.fromtimestamp(
            fill["time"] / 1000,
            timezone.utc
        )

        print(
            f"{fill_time} | "
            f"{fill.get('coin')} | "
            f"side={fill.get('side')} | "
            f"dir={fill.get('dir')} | "
            f"sz={fill.get('sz')} | "
            f"px={fill.get('px')} | "
            f"closedPnl={fill.get('closedPnl')} | "
            f"fee={fill.get('fee')}"
        )

    print()


# ============================================================
# REALISED P&L
# ============================================================

closed_pnl = sum(
    float(
        x.get(
            "closedPnl",
            0
        )
    )
    for x in today_fills
)


# ============================================================
# FEES
# ============================================================

fees = sum(
    abs(
        float(
            x.get(
                "fee",
                0
            )
        )
    )
    for x in today_fills
)


# ============================================================
# NET P&L
# ============================================================

net_pnl = (
    closed_pnl
    - fees
)


# ============================================================
# ENTRY / REDUCTION BREAKDOWN
# ============================================================

long_entries = 0
short_entries = 0

long_reductions = 0
short_reductions = 0


for fill in today_fills:

    side = str(
        fill.get(
            "side",
            ""
        )
    ).upper()

    closed_value = float(
        fill.get(
            "closedPnl",
            0
        )
    )

    direction = str(
        fill.get(
            "dir",
            ""
        )
    ).lower()


    # --------------------------------------------------------
    # Use Hyperliquid's "dir" field where available
    # --------------------------------------------------------

    if "open long" in direction:

        long_entries += 1

    elif "open short" in direction:

        short_entries += 1

    elif (
        "long" in direction
        and (
            "close" in direction
            or "reduce" in direction
        )
    ):

        long_reductions += 1

    elif (
        "short" in direction
        and (
            "close" in direction
            or "reduce" in direction
        )
    ):

        short_reductions += 1

    else:

        # Fallback based on closed P&L

        if side in ("B", "BUY"):

            if abs(closed_value) > 0:

                long_reductions += 1

            else:

                long_entries += 1


        elif side in ("A", "SELL"):

            if abs(closed_value) > 0:

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

Perp Equity:             ${perp_equity:,.2f}
USDC Balance:            ${usdc_balance:,.2f}
Position Value:          ${position_value:,.2f}
Margin Used:             ${margin_used:,.2f}
Withdrawable:            ${withdrawable:,.2f}

Open Positions:          {len(positions)}


TODAY'S TRADING
---------------

Fills:                   {len(today_fills)}

Long Entries:            {long_entries}
Short Entries:           {short_entries}

Long Reductions:         {long_reductions}
Short Reductions:        {short_reductions}


P&L
---

Realised P&L:            ${closed_pnl:,.2f}
Trading Fees:            ${fees:,.2f}

NET P&L:                 ${net_pnl:,.2f}
"""


# ============================================================
# PRINT REPORT
# ============================================================

print("=" * 70)
print("EMAIL REPORT")
print("=" * 70)

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

    print(
        email
    )

except Exception as e:

    print(
        "Failed to send email."
    )

    print(
        e
    )

    raise
