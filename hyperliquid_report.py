import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime


# ============================================================
# CONFIG
# ============================================================

API_URL = "https://api.hyperliquid.xyz/info"

# Wallet is stored in GitHub Secrets
WALLET = os.environ["HYPERLIQUID_WALLET"]

HISTORY_FILE = "account_history.csv"
REPORT_FILE = "hyperliquid_daily_report.txt"


# ============================================================
# HYPERLIQUID API
# ============================================================

def hl_info(payload):

    response = requests.post(
        API_URL,
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
    # NUMERIC
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

        df["datetime_london"] = (
            df["datetime"]
            .dt
            .tz_convert("Europe/London")
        )

        df["date"] = (
            df["datetime_london"]
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

        df["notional"] = 0.0

    # --------------------------------------------------------
    # FEE
    # --------------------------------------------------------
    #
    # Keep fee completely separate.
    #
    # We do NOT use it to calculate the actual account P&L.
    #
    # This is only for reporting.
    #
    # --------------------------------------------------------

    if "fee" in df.columns:

        df["feeCost"] = (
            df["fee"]
            .abs()
        )

    else:

        df["feeCost"] = 0.0

    return df


# ============================================================
# PREPARE FUNDING
# ============================================================

def prepare_funding(df):

    if df.empty:
        return df

    df = df.copy()

    # --------------------------------------------------------
    # FUNDING
    # --------------------------------------------------------

    if "delta" in df.columns:

        def extract_funding(x):

            if isinstance(x, dict):

                if "usdc" in x:

                    try:
                        return float(
                            x["usdc"]
                        )
                    except Exception:
                        return 0.0

            return 0.0

        df["fundingPnl"] = (
            df["delta"]
            .apply(extract_funding)
        )

    else:

        df["fundingPnl"] = 0.0

    # --------------------------------------------------------
    # DATETIME
    # --------------------------------------------------------

    if "time" in df.columns:

        df["datetime"] = pd.to_datetime(
            df["time"],
            unit="ms",
            utc=True
        )

        df["datetime_london"] = (
            df["datetime"]
            .dt
            .tz_convert("Europe/London")
        )

        df["date"] = (
            df["datetime_london"]
            .dt
            .date
        )

    return df


# ============================================================
# ACCOUNT HISTORY
# ============================================================

def load_history():

    if not os.path.exists(
        HISTORY_FILE
    ):

        return pd.DataFrame(
            columns=[
                "date",
                "account_value",
                "daily_pnl"
            ]
        )

    try:

        df = pd.read_csv(
            HISTORY_FILE
        )

        if not df.empty:

            df["date"] = pd.to_datetime(
                df["date"]
            ).dt.date

            df["account_value"] = pd.to_numeric(
                df["account_value"],
                errors="coerce"
            )

            df["daily_pnl"] = pd.to_numeric(
                df["daily_pnl"],
                errors="coerce"
            )

        return df

    except Exception:

        return pd.DataFrame(
            columns=[
                "date",
                "account_value",
                "daily_pnl"
            ]
        )


# ============================================================
# UPDATE ACCOUNT HISTORY
# ============================================================

def update_history(
    history,
    today,
    account_value
):

    history = history.copy()

    # --------------------------------------------------------
    # Previous account value
    # --------------------------------------------------------

    previous_value = None

    if not history.empty:

        previous_rows = (
            history[
                history["date"] < today
            ]
            .sort_values("date")
        )

        if not previous_rows.empty:

            previous_value = float(
                previous_rows.iloc[-1]
                ["account_value"]
            )

    # --------------------------------------------------------
    # Actual daily P&L
    # --------------------------------------------------------
    #
    # IMPORTANT:
    #
    # This is NOT:
    #
    # closedPnl + fees + funding
    #
    # It is simply:
    #
    # today's account value
    # minus
    # previous recorded account value
    #
    # --------------------------------------------------------

    if previous_value is None:

        daily_pnl = np.nan

    else:

        daily_pnl = (
            account_value -
            previous_value
        )

    # --------------------------------------------------------
    # Remove today's existing row
    # --------------------------------------------------------

    history = history[
        history["date"] != today
    ]

    # --------------------------------------------------------
    # Add today's row
    # --------------------------------------------------------

    new_row = pd.DataFrame({

        "date": [
            today
        ],

        "account_value": [
            account_value
        ],

        "daily_pnl": [
            daily_pnl
        ]
    })

    history = pd.concat(
        [
            history,
            new_row
        ],
        ignore_index=True
    )

    history = (
        history
        .sort_values("date")
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    history.to_csv(
        HISTORY_FILE,
        index=False
    )

    return history, previous_value, daily_pnl


# ============================================================
# TODAY'S TRADING DATA
# ============================================================

def calculate_today_stats(
    fills,
    funding,
    today
):

    # --------------------------------------------------------
    # FILLS
    # --------------------------------------------------------

    if not fills.empty:

        today_fills = fills[
            fills["date"] == today
        ]

    else:

        today_fills = pd.DataFrame()

    if not today_fills.empty:

        closed_pnl = (
            today_fills[
                "closedPnl"
            ]
            .sum()
        )

        fees = (
            today_fills[
                "feeCost"
            ]
            .sum()
        )

        volume = (
            today_fills[
                "notional"
            ]
            .sum()
        )

        fills_count = len(
            today_fills
        )

    else:

        closed_pnl = 0.0
        fees = 0.0
        volume = 0.0
        fills_count = 0

    # --------------------------------------------------------
    # FUNDING
    # --------------------------------------------------------

    if not funding.empty:

        today_funding = funding[
            funding["date"] == today
        ]

        funding_pnl = (
            today_funding[
                "fundingPnl"
            ]
            .sum()
        )

    else:

        funding_pnl = 0.0

    return {

        "closed_pnl": closed_pnl,

        "fees": fees,

        "funding": funding_pnl,

        "volume": volume,

        "fills": fills_count
    }


# ============================================================
# ALL-TIME FILL STATISTICS
# ============================================================

def calculate_fill_stats(fills):

    if fills.empty:

        return {

            "fills": 0,

            "closed_pnl": 0.0,

            "fees": 0.0,

            "volume": 0.0,

            "winning_fills": 0,

            "losing_fills": 0,

            "win_rate": 0.0
        }

    closed = (
        fills["closedPnl"]
        .fillna(0)
    )

    fees = (
        fills["feeCost"]
        .fillna(0)
    )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # We calculate this ONLY as an execution statistic.
    #
    # It is NOT used as actual account P&L.
    #
    # --------------------------------------------------------

    execution_net = (
        closed -
        fees
    )

    winners = (
        execution_net > 0
    ).sum()

    losers = (
        execution_net < 0
    ).sum()

    total = (
        winners +
        losers
    )

    if total > 0:

        win_rate = (
            winners /
            total
        )

    else:

        win_rate = 0.0

    return {

        "fills": len(fills),

        "closed_pnl": closed.sum(),

        "fees": fees.sum(),

        "volume": fills[
            "notional"
        ].sum(),

        "winning_fills": winners,

        "losing_fills": losers,

        "win_rate": win_rate
    }


# ============================================================
# P&L BY COIN
# ============================================================

def pnl_by_coin(df):

    if df.empty:
        return pd.DataFrame()

    result = (

        df.groupby("coin")

        .agg(

            Fills=(
                "coin",
                "count"
            ),

            ClosedPnL=(
                "closedPnl",
                "sum"
            ),

            Fees=(
                "feeCost",
                "sum"
            ),

            Volume=(
                "notional",
                "sum"
            )
        )

        .sort_values(
            "ClosedPnL",
            ascending=False
        )
    )

    return result


# ============================================================
# LONG / SHORT
# ============================================================

def long_short_stats(df):

    if df.empty:
        return pd.DataFrame()

    df = df.copy()

    df["direction"] = np.where(
        df["side"] == "B",
        "Long",
        "Short"
    )

    result = (

        df.groupby("direction")

        .agg(

            Fills=(
                "direction",
                "count"
            ),

            ClosedPnL=(
                "closedPnl",
                "sum"
            ),

            Fees=(
                "feeCost",
                "sum"
            ),

            Volume=(
                "notional",
                "sum"
            )
        )
    )

    return result


# ============================================================
# DAILY CLOSED P&L HISTORY
# ============================================================

def daily_closed_pnl(fills):

    if fills.empty:

        return pd.DataFrame()

    daily = (

        fills.groupby("date")

        .agg(

            Fills=(
                "coin",
                "count"
            ),

            ClosedPnL=(
                "closedPnl",
                "sum"
            ),

            Fees=(
                "feeCost",
                "sum"
            ),

            Volume=(
                "notional",
                "sum"
            )
        )
    )

    return daily.sort_index()


# ============================================================
# MAX DRAWDOWN FROM ACTUAL ACCOUNT VALUE
# ============================================================

def calculate_account_drawdown(
    history
):

    if history.empty:

        return 0.0

    values = (
        history
        .sort_values("date")
        ["account_value"]
    )

    running_max = (
        values
        .cummax()
    )

    drawdown = (
        values -
        running_max
    )

    return drawdown.min()


# ============================================================
# CREATE REPORT
# ============================================================

def create_report(
    account,
    today_stats,
    fill_stats,
    history,
    previous_value,
    daily_pnl,
    total_funding,
    max_drawdown,
    coin_stats,
    direction_stats,
    daily_closed
):

    margin = (
        account["marginSummary"]
    )

    account_value = float(
        margin["accountValue"]
    )

    margin_used = float(
        margin["totalMarginUsed"]
    )

    position_notional = float(
        margin["totalNtlPos"]
    )

    withdrawable = float(
        account["withdrawable"]
    )

    today = (
        pd.Timestamp.now(
            tz="Europe/London"
        )
        .strftime("%d %B %Y")
    )

    lines = []

    # ========================================================
    # HEADER
    # ========================================================

    lines.append(
        "=" * 70
    )

    lines.append(
        "HYPERLIQUID DAILY REPORT"
    )

    lines.append(
        today
    )

    lines.append(
        "=" * 70
    )

    # ========================================================
    # ACCOUNT
    # ========================================================

    lines.append("")
    lines.append(
        "--- ACCOUNT ---"
    )

    lines.append(
        f"Account value:       ${account_value:,.2f}"
    )

    if previous_value is not None:

        lines.append(
            f"Previous value:      ${previous_value:,.2f}"
        )

        lines.append(
            f"ACTUAL DAILY P&L:    ${daily_pnl:,.2f}"
        )

    else:

        lines.append(
            "Previous value:      N/A - first day"
        )

        lines.append(
            "ACTUAL DAILY P&L:    N/A - first day"
        )

    lines.append(
        f"Margin used:         ${margin_used:,.2f}"
    )

    lines.append(
        f"Position notional:   ${position_notional:,.2f}"
    )

    lines.append(
        f"Withdrawable:        ${withdrawable:,.2f}"
    )

    # ========================================================
    # TODAY'S TRADING
    # ========================================================

    lines.append("")
    lines.append(
        "--- TODAY'S TRADING ---"
    )

    lines.append(
        f"Fills:               {today_stats['fills']}"
    )

    lines.append(
        f"Closed P&L:          ${today_stats['closed_pnl']:,.2f}"
    )

    lines.append(
        f"Trading fees:        ${today_stats['fees']:,.2f}"
    )

    lines.append(
        f"Funding:             ${today_stats['funding']:,.2f}"
    )

    lines.append(
        f"Volume:              ${today_stats['volume']:,.2f}"
    )

    # ========================================================
    # IMPORTANT RECONCILIATION
    # ========================================================

    lines.append("")
    lines.append(
        "--- P&L RECONCILIATION ---"
    )

    lines.append(
        "The figures below are shown separately."
    )

    lines.append(
        "They are NOT added together to calculate"
    )

    lines.append(
        "the actual daily account P&L."
    )

    lines.append("")

    lines.append(
        f"Closed P&L:          ${today_stats['closed_pnl']:,.2f}"
    )

    lines.append(
        f"Fees:               -${today_stats['fees']:,.2f}"
    )

    lines.append(
        f"Funding:             ${today_stats['funding']:,.2f}"
    )

    lines.append("")

    if daily_pnl is not None:

        lines.append(
            f"ACTUAL ACCOUNT P&L: ${daily_pnl:,.2f}"
        )

    else:

        lines.append(
            "ACTUAL ACCOUNT P&L: N/A"
        )

    # ========================================================
    # ALL TIME
    # ========================================================

    lines.append("")
    lines.append(
        "--- ALL-TIME FILL STATISTICS ---"
    )

    lines.append(
        f"Total fills:         {fill_stats['fills']}"
    )

    lines.append(
        f"Closed P&L:          ${fill_stats['closed_pnl']:,.2f}"
    )

    lines.append(
        f"Trading fees:        ${fill_stats['fees']:,.2f}"
    )

    lines.append(
        f"Total volume:        ${fill_stats['volume']:,.2f}"
    )

    lines.append(
        f"Winning fills:       {fill_stats['winning_fills']}"
    )

    lines.append(
        f"Losing fills:        {fill_stats['losing_fills']}"
    )

    lines.append(
        f"Win rate:            {fill_stats['win_rate']:.2%}"
    )

    # ========================================================
    # RISK
    # ========================================================

    lines.append("")
    lines.append(
        "--- RISK ---"
    )

    lines.append(
        f"Account max drawdown: ${max_drawdown:,.2f}"
    )

    # ========================================================
    # BY COIN
    # ========================================================

    lines.append("")
    lines.append(
        "--- BY COIN ---"
    )

    if not coin_stats.empty:

        lines.append(
            coin_stats.to_string(
                float_format=lambda x:
                f"{x:,.2f}"
            )
        )

    else:

        lines.append(
            "No trading data."
        )

    # ========================================================
    # LONG / SHORT
    # ========================================================

    lines.append("")
    lines.append(
        "--- LONG / SHORT ---"
    )

    if not direction_stats.empty:

        lines.append(
            direction_stats.to_string(
                float_format=lambda x:
                f"{x:,.2f}"
            )
        )

    else:

        lines.append(
            "No trading data."
        )

    # ========================================================
    # DAILY ACCOUNT HISTORY
    # ========================================================

    lines.append("")
    lines.append(
        "--- ACCOUNT VALUE HISTORY ---"
    )

    if not history.empty:

        history_display = (
            history
            .tail(20)
            .copy()
        )

        history_display["date"] = (
            history_display["date"]
            .astype(str)
        )

        lines.append(
            history_display.to_string(
                index=False,
                float_format=lambda x:
                f"{x:,.2f}"
            )
        )

    # ========================================================
    # DAILY CLOSED P&L
    # ========================================================

    lines.append("")
    lines.append(
        "--- RECENT CLOSED P&L ---"
    )

    if not daily_closed.empty:

        lines.append(
            daily_closed
            .tail(20)
            .to_string(
                float_format=lambda x:
                f"{x:,.2f}"
            )
        )

    # ========================================================
    # FOOTER
    # ========================================================

    lines.append("")
    lines.append(
        "=" * 70
    )

    lines.append(
        "END OF REPORT"
    )

    lines.append(
        "=" * 70
    )

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print(
        "Connecting to Hyperliquid..."
    )

    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    account = (
        get_account_state()
    )

    fills = (
        get_fills()
    )

    funding = (
        get_funding()
    )

    print(
        f"Downloaded {len(fills)} fills."
    )

    print(
        f"Downloaded {len(funding)} funding records."
    )

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

    margin = (
        account["marginSummary"]
    )

    account_value = float(
        margin["accountValue"]
    )

    # --------------------------------------------------------
    # TODAY
    # --------------------------------------------------------

    today = (
        pd.Timestamp.now(
            tz="Europe/London"
        )
        .date()
    )

    # --------------------------------------------------------
    # LOAD HISTORY
    # --------------------------------------------------------

    history = (
        load_history()
    )

    # --------------------------------------------------------
    # UPDATE HISTORY
    # --------------------------------------------------------

    (
        history,
        previous_value,
        daily_pnl
    ) = update_history(
        history=history,
        today=today,
        account_value=account_value
    )

    # --------------------------------------------------------
    # TODAY STATS
    # --------------------------------------------------------

    today_stats = (
        calculate_today_stats(
            fills,
            funding,
            today
        )
    )

    # --------------------------------------------------------
    # ALL FILL STATS
    # --------------------------------------------------------

    fill_stats = (
        calculate_fill_stats(
            fills
        )
    )

    # --------------------------------------------------------
    # FUNDING
    # --------------------------------------------------------

    if (
        funding is not None
        and not funding.empty
    ):

        total_funding = (
            funding[
                "fundingPnl"
            ]
            .sum()
        )

    else:

        total_funding = 0.0

    # --------------------------------------------------------
    # COIN
    # --------------------------------------------------------

    coin_stats = (
        pnl_by_coin(
            fills
        )
    )

    # --------------------------------------------------------
    # LONG / SHORT
    # --------------------------------------------------------

    direction_stats = (
        long_short_stats(
            fills
        )
    )

    # --------------------------------------------------------
    # DAILY CLOSED P&L
    # --------------------------------------------------------

    daily_closed = (
        daily_closed_pnl(
            fills
        )
    )

    # --------------------------------------------------------
    # DRAWDOWN
    # --------------------------------------------------------

    max_drawdown = (
        calculate_account_drawdown(
            history
        )
    )

    # --------------------------------------------------------
    # CREATE REPORT
    # --------------------------------------------------------

    report = create_report(

        account=account,

        today_stats=today_stats,

        fill_stats=fill_stats,

        history=history,

        previous_value=previous_value,

        daily_pnl=daily_pnl,

        total_funding=total_funding,

        max_drawdown=max_drawdown,

        coin_stats=coin_stats,

        direction_stats=direction_stats,

        daily_closed=daily_closed
    )

    # --------------------------------------------------------
    # PRINT TO GITHUB
    # --------------------------------------------------------

    print("")
    print(report)

    # --------------------------------------------------------
    # SAVE REPORT
    # --------------------------------------------------------

    with open(
        REPORT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(report)

    print("")
    print(
        f"Report saved as {REPORT_FILE}"
    )

    print(
        f"History saved as {HISTORY_FILE}"
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
