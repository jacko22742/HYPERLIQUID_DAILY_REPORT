import os
import requests
from datetime import datetime, timezone

WALLET = os.environ["HYPERLIQUID_WALLET"]

url = "https://api.hyperliquid.xyz/info"

# Get fills
r = requests.post(url, json={
    "type": "userFills",
    "user": WALLET,
    "aggregateByTime": False
})

fills = r.json()

# Today's date
today = datetime.now(timezone.utc).date()

# Today's fills
today_fills = [
    x for x in fills
    if datetime.fromtimestamp(
        x["time"] / 1000,
        timezone.utc
    ).date() == today
]

# P&L after fees
pnl = sum(
    float(x.get("closedPnl", 0)) - abs(float(x.get("fee", 0)))
    for x in today_fills
)

print("=" * 40)
print("HYPERLIQUID DAILY REPORT")
print("=" * 40)

print(f"Date:       {today}")
print(f"Trades:     {len(today_fills)}")
print(f"Net P&L:    ${pnl:,.2f}")

print("=" * 40)
