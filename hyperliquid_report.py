import os
import requests
import pandas as pd
import numpy as np


# ============================================================
# CONFIG
# ============================================================

API_URL = "https://api.hyperliquid.xyz/info"

WALLET = os.environ["HYPERLIQUID_WALLET"]


# ============================================================
# HYPERLIQUID API
# ============================================================

def hl_info(payload):

    response = requests.post(
        API_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# ACCOUNT
# ============================================================

def get_account_state():

    return hl_info({
        "type": "clearinghouseState",
        "user": WALLET
    })


# ============================================================
# FILLS
# ============================================================

def get_fills():

    data = hl_info({
        "type": "userFills",
        "user": WALLET,
        "aggregateByTime": False
    })

    return pd.DataFrame(data)


# ============================================================
# FUNDING
# ============================================================

def get_funding():

    data = hl_info({
        "type": "userFunding",
        "user": WALLET,
        "startTime": 0
    })

    return pd.DataFrame(data)


# ============================================================
# PREPARE FILLS
# ============================================================

def prepare_fills(df):

    if df.empty:
        return df

    df = df.copy()

    # --------------------------------------------------------
    # NUMERIC COLUMNS
    # --------------------------------------------------------

    for col in [
        "px",
        "sz",
        "closedPnl",
        "fee"
    ]:

        if col in df.columns:

            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            ).fillna(0)

    # --------------------------------------------------------
    # DATETIME
    # --------------------------------------------------------

    if "time" in df.columns:

        df["datetime"] = pd.to_datetime(
            df["time"],
            unit="ms",
            utc=True
        )

        df["date"] = (
            df["datetime"]
            .dt
            .date
        )

    # --------------------------------------------------------
    # NOTIONAL
    # --------------------------------------------------------

    if (
        "px" in df.columns
        and "sz" in df.columns
    ):

        df["notional"] = (
            df["px"] *
            df["sz"]
        )

    else:

        df["notional"] = 0

    # --------------------------------------------------------
    # NET P&L
    # --------------------------------------------------------
    #
    # Hyperliquid's fee is normally negative.
    #
    # Example:
    #
    # closedPnl = 100
    # fee       = -2
    #
    # net P&L   = 98
    #
    # --------------------------------------------------------

    df["netTradingPnl"] = (
        df["closedPnl"] +
        df["fee"]
    )

    return df


# ============================================================
# PREPARE FUNDING
# ============================================================

def prepare_funding(df):

    if df.empty:
        return df

    df = df.copy()

    # --------------------------------------------------------
    # FUNDING AMOUNT
    # --------------------------------------------------------

    if "delta" in df.columns:

        def get_amount(x):

            if isinstance(x, dict):

                if "usdc" in x:

                    try:
                        return float(x["usdc"])
                    except Exception:
                        return 0.0

                if "coin" in x:

                    try:
                        return float(x["coin"])
                    except Exception:
                        return 0.0

            try:
                return float(x)
            except Exception:
                return 0.0

        df["fundingPnl"] = (
            df["delta"]
            .apply(get_amount)
        )

    elif "amount" in df.columns:

        df["fundingPnl"] = pd.to_numeric(
            df["amount"],
            errors="coerce"
        ).fillna(0)

    else:

        df["fundingPnl"] = 0.0

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    if "time" in df.columns:

        df["datetime"] = pd.to_datetime(
            df["time"],
            unit="ms",
            utc=True
        )

        df["date"] = (
            df["datetime"]
            .dt
            .date
        )

    return df


# ============================================================
# GET TODAY'S P&L
# ============================================================

def calculate_today_pnl(fills, funding):

    # London date
    today = pd.Timestamp.now(
        tz="Europe/London"
    ).date()

    # --------------------------------------------------------
    # TRADING P&L
    # --------------------------------------------------------

    if not fills.empty:

        today_fills = fills[
            fills["date"] == today
        ]

        gross_pnl = (
            today_fills["closedPnl"]
            .sum()
        )

        fees = (
            today_fills["fee"]
            .sum()
        )

        net_trading_pnl = (
            today_fills["netTradingPnl"]
            .sum()
        )

        volume = (
            today_fills["notional"]
            .sum()
        )

        fills_count = len(
            today_fills
        )

    else:

        gross_pnl = 0
        fees = 0
        net_trading_pnl = 0
        volume = 0
        fills_count = 0

    # --------------------------------------------------------
    # FUNDING
    # --------------------------------------------------------

    if not funding.empty:

        today_funding = funding[
            funding["date"] == today
        ]

        funding_pnl = (
            today_funding["fundingPnl"]
            .sum()
        )

    else:

        funding_pnl = 0

    # --------------------------------------------------------
    # TOTAL
    # --------------------------------------------------------

    total_net_pnl = (
        net_trading_pnl +
        funding_pnl
    )

    return {
        "gross_pnl": gross_pnl,
        "fees": fees,
        "net_trading_pnl": net_trading_pnl,
        "funding": funding_pnl,
        "net_pnl": total_net_pnl,
        "volume": volume,
        "fills": fills_count
    }


# ============================================================
# ALL-TIME STATS
# ============================================================

def calculate_all_time_stats(fills):

    if fills.empty:

        return {
            "gross_pnl": 0,
            "fees": 0,
            "net_pnl": 0,
            "volume": 0
        }

    gross_pnl = (
        fills["closedPnl"]
        .sum()
    )

    fees = (
        fills["fee"]
        .sum()
    )

    net_pnl = (
        fills["netTradingPnl"]
        .sum()
    )

    volume = (
        fills["notional"]
        .sum()
    )

    return {
        "gross_pnl": gross_pnl,
        "fees": fees,
        "net_pnl": net_pnl,
        "volume": volume
    }


# ============================================================
# WIN RATE
# ============================================================

def calculate_win_rate(fills):

    if fills.empty:
        return 0

    pnl = (
        fills["netTradingPnl"]
    )

    winners = (
        pnl > 0
    ).sum()

    losers = (
        pnl < 0
    ).sum()

    total = (
        winners +
        losers
    )

    if total == 0:
        return 0

    return winners / total


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 70)
    print("HYPERLIQUID DAILY REPORT")
    print("=" * 70)

    print("")
    print("Wallet:")
    print(WALLET)

    # --------------------------------------------------------
    # API
    # --------------------------------------------------------

    print("")
    print("Downloading account data...")

    account = get_account_state()

    print("Downloading fills...")

    fills = get_fills()

    print("Downloading funding...")

    funding = get_funding()

    # --------------------------------------------------------
    # PREPARE
    # --------------------------------------------------------

    fills = prepare_fills(
        fills
    )

    funding = prepare_funding(
        funding
    )

    # --------------------------------------------------------
    # ACCOUNT VALUE
    # --------------------------------------------------------

    margin = account[
        "marginSummary"
    ]

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

    # --------------------------------------------------------
    # TODAY
    # --------------------------------------------------------

    today = calculate_today_pnl(
        fills,
        funding
    )

    # --------------------------------------------------------
    # ALL TIME
    # --------------------------------------------------------

    all_time = calculate_all_time_stats(
        fills
    )

    # --------------------------------------------------------
    # WIN RATE
    # --------------------------------------------------------

    win_rate = calculate_win_rate(
        fills
    )

    # ========================================================
    # REPORT
    # ========================================================

    print("")
    print("-" * 70)
    print("ACCOUNT")
    print("-" * 70)

    print(
        f"Account value:       "
        f"${account_value:,.2f}"
    )

    print(
        f"Margin used:         "
        f"${margin_used:,.2f}"
    )

    print(
        f"Position notional:   "
        f"${position_value:,.2f}"
    )

    print(
        f"Withdrawable:        "
        f"${withdrawable:,.2f}"
    )

    # ========================================================

    print("")
    print("-" * 70)
    print("TODAY")
    print("-" * 70)

    print(
        f"Gross P&L:           "
        f"${today['gross_pnl']:,.2f}"
    )

    print(
        f"Trading fees:        "
        f"${today['fees']:,.2f}"
    )

    print(
        f"Net trading P&L:     "
        f"${today['net_trading_pnl']:,.2f}"
    )

    print(
        f"Funding:             "
        f"${today['funding']:,.2f}"
    )

    print(
        f"NET P&L:             "
        f"${today['net_pnl']:,.2f}"
    )

    print(
        f"Volume:              "
        f"${today['volume']:,.2f}"
    )

    print(
        f"Fills:               "
        f"{today['fills']}"
    )

    # ========================================================

    print("")
    print("-" * 70)
    print("ALL TIME")
    print("-" * 70)

    print(
        f"Gross P&L:           "
        f"${all_time['gross_pnl']:,.2f}"
    )

    print(
        f"Total fees:          "
        f"${all_time['fees']:,.2f}"
    )

    print(
        f"Net trading P&L:     "
        f"${all_time['net_pnl']:,.2f}"
    )

    print(
        f"Total volume:        "
        f"${all_time['volume']:,.2f}"
    )

    print(
        f"Win rate:            "
        f"{win_rate:.2%}"
    )

    # ========================================================

    print("")
    print("=" * 70)
    print("REPORT COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
