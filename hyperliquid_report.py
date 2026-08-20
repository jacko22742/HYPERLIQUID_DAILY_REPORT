import os
import requests
import pandas as pd
import numpy as np


# ============================================================
# CONFIG
# ============================================================

API_URL = "https://api.hyperliquid.xyz/info"

# Wallet comes from GitHub Actions Secret
WALLET = os.environ["HYPERLIQUID_WALLET"]


# ============================================================
# HYPERLIQUID API REQUEST
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

    fills = hl_info({
        "type": "userFills",
        "user": WALLET,
        "aggregateByTime": False
    })

    return pd.DataFrame(fills)


# ============================================================
# FUNDING
# ============================================================

def get_funding():

    funding = hl_info({
        "type": "userFunding",
        "user": WALLET,
        "startTime": 0
    })

    return pd.DataFrame(funding)


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

        df["hour"] = (
            df["datetime_london"]
            .dt
            .hour
        )

        df["day"] = (
            df["datetime_london"]
            .dt
            .day_name()
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
    # IMPORTANT:
    #
    # Hyperliquid fee represents a COST.
    #
    # We use ABS() so that regardless of whether the API
    # returns:
    #
    #     fee = 2.50
    #
    # or:
    #
    #     fee = -2.50
    #
    # the cost is always treated as:
    #
    #     -2.50
    #
    # --------------------------------------------------------

    df["feeCost"] = (
        df["fee"]
        .abs()
    )

    # --------------------------------------------------------
    # NET TRADING P&L
    # --------------------------------------------------------
    #
    # Closed P&L is the realised trading result.
    #
    # Fees are a cost.
    #
    # Therefore:
    #
    # NET = CLOSED P&L - FEE COST
    #
    # --------------------------------------------------------

    df["netTradingPnl"] = (
        df["closedPnl"] -
        df["feeCost"]
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
    # HYPERLIQUID FUNDING
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
# BASIC STATISTICS
# ============================================================

def calculate_stats(df):

    stats = {}

    if df.empty:
        return stats

    gross_pnl = (
        df["closedPnl"]
        .fillna(0)
    )

    fees = (
        df["feeCost"]
        .fillna(0)
    )

    net_pnl = (
        df["netTradingPnl"]
        .fillna(0)
    )

    stats["Total fills"] = len(df)

    # --------------------------------------------------------
    # GROSS P&L
    # --------------------------------------------------------

    stats["Gross realised P&L"] = (
        gross_pnl.sum()
    )

    # --------------------------------------------------------
    # FEES
    # --------------------------------------------------------

    stats["Total trading fees"] = (
        fees.sum()
    )

    # --------------------------------------------------------
    # NET P&L
    # --------------------------------------------------------

    stats["Net trading P&L"] = (
        net_pnl.sum()
    )

    # --------------------------------------------------------
    # PROFIT / LOSS
    # --------------------------------------------------------

    stats["Gross profit"] = (
        net_pnl[
            net_pnl > 0
        ].sum()
    )

    stats["Gross loss"] = (
        net_pnl[
            net_pnl < 0
        ].sum()
    )

    # --------------------------------------------------------
    # WINNING / LOSING FILLS
    # --------------------------------------------------------

    stats["Winning fills"] = (
        net_pnl > 0
    ).sum()

    stats["Losing fills"] = (
        net_pnl < 0
    ).sum()

    total_decided = (
        stats["Winning fills"] +
        stats["Losing fills"]
    )

    stats["Win rate"] = (
        stats["Winning fills"] /
        max(total_decided, 1)
    )

    # --------------------------------------------------------
    # PROFIT FACTOR
    # --------------------------------------------------------

    if abs(stats["Gross loss"]) > 0:

        stats["Profit factor"] = (
            stats["Gross profit"] /
            abs(stats["Gross loss"])
        )

    else:

        stats["Profit factor"] = np.inf

    # --------------------------------------------------------
    # AVERAGES
    # --------------------------------------------------------

    stats["Average net fill P&L"] = (
        net_pnl.mean()
    )

    stats["Average winner"] = (

        net_pnl[
            net_pnl > 0
        ].mean()

        if (
            net_pnl > 0
        ).any()

        else 0
    )

    stats["Average loser"] = (

        net_pnl[
            net_pnl < 0
        ].mean()

        if (
            net_pnl < 0
        ).any()

        else 0
    )

    stats["Largest winner"] = (
        net_pnl.max()
    )

    stats["Largest loser"] = (
        net_pnl.min()
    )

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    stats["Total volume"] = (
        df["notional"].sum()
    )

    return stats


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

            GrossPnL=(
                "closedPnl",
                "sum"
            ),

            Fees=(
                "feeCost",
                "sum"
            ),

            NetPnL=(
                "netTradingPnl",
                "sum"
            ),

            Volume=(
                "notional",
                "sum"
            )
        )

        .sort_values(
            "NetPnL",
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

    return (

        df.groupby("direction")

        .agg(

            Fills=(
                "direction",
                "count"
            ),

            GrossPnL=(
                "closedPnl",
                "sum"
            ),

            Fees=(
                "feeCost",
                "sum"
            ),

            NetPnL=(
                "netTradingPnl",
                "sum"
            ),

            Volume=(
                "notional",
                "sum"
            )
        )
    )


# ============================================================
# DAILY P&L
# ============================================================

def daily_pnl(
    fills,
    funding
):

    if fills.empty:
        return pd.DataFrame()

    # --------------------------------------------------------
    # TRADING P&L
    # --------------------------------------------------------

    daily = (

        fills.groupby("date")

        .agg(

            Fills=(
                "coin",
                "count"
            ),

            GrossPnL=(
                "closedPnl",
                "sum"
            ),

            Fees=(
                "feeCost",
                "sum"
            ),

            NetTradingPnL=(
                "netTradingPnl",
                "sum"
            ),

            Volume=(
                "notional",
                "sum"
            )
        )
    )

    # --------------------------------------------------------
    # FUNDING
    # --------------------------------------------------------

    if (
        funding is not None
        and not funding.empty
    ):

        funding_daily = (

            funding
            .groupby("date")
            ["fundingPnl"]
            .sum()
            .rename("FundingPnL")
        )

        daily = daily.join(
            funding_daily,
            how="left"
        )

    else:

        daily["FundingPnL"] = 0.0

    daily["FundingPnL"] = (
        daily["FundingPnL"]
        .fillna(0)
    )

    # --------------------------------------------------------
    # TOTAL NET P&L
    # --------------------------------------------------------

    daily["NetPnL"] = (
        daily["NetTradingPnL"] +
        daily["FundingPnL"]
    )

    return daily.sort_index()


# ============================================================
# MAX DRAWDOWN
# ============================================================

def calculate_drawdown(daily):

    if daily.empty:
        return 0.0

    equity = (
        daily["NetPnL"]
        .cumsum()
    )

    running_max = (
        equity.cummax()
    )

    drawdown = (
        equity -
        running_max
    )

    return drawdown.min()


# ============================================================
# CREATE REPORT
# ============================================================

def create_report(
    account,
    stats,
    total_funding,
    max_dd,
    coin_stats,
    direction_stats,
    daily
):

    margin = account[
        "marginSummary"
    ]

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

    # --------------------------------------------------------
    # TOTAL NET P&L
    # --------------------------------------------------------

    net_total = (
        stats["Net trading P&L"] +
        total_funding
    )

    report_date = (
        pd.Timestamp.now(
            tz="Europe/London"
        )
        .strftime("%d %B %Y")
    )

    lines = []

    lines.append(
        "=" * 70
    )

    lines.append(
        "HYPERLIQUID DAILY REPORT"
    )

    lines.append(
        report_date
    )

    lines.append(
        "=" * 70
    )

    # ========================================================
    # ACCOUNT
    # ========================================================

    lines.append("")
    lines.append("--- ACCOUNT ---")

    lines.append(
        f"Account value:       ${account_value:,.2f}"
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
    # TRADING
    # ========================================================

    lines.append("")
    lines.append("--- TRADING ---")

    lines.append(
        f"Total fills:         {stats['Total fills']}"
    )

    lines.append(
        f"Gross realised P&L:  ${stats['Gross realised P&L']:,.2f}"
    )

    lines.append(
        f"Trading fees:        -${stats['Total trading fees']:,.2f}"
    )

    lines.append(
        f"Net trading P&L:     ${stats['Net trading P&L']:,.2f}"
    )

    lines.append(
        f"Funding P&L:         ${total_funding:,.2f}"
    )

    lines.append(
        f"NET P&L:             ${net_total:,.2f}"
    )

    lines.append(
        f"Win rate:            {stats['Win rate']:.2%}"
    )

    if np.isinf(
        stats["Profit factor"]
    ):

        lines.append(
            "Profit factor:       Infinite"
        )

    else:

        lines.append(
            f"Profit factor:       {stats['Profit factor']:.2f}"
        )

    lines.append(
        f"Average fill P&L:    ${stats['Average net fill P&L']:,.2f}"
    )

    lines.append(
        f"Largest winner:      ${stats['Largest winner']:,.2f}"
    )

    lines.append(
        f"Largest loser:       ${stats['Largest loser']:,.2f}"
    )

    lines.append(
        f"Total volume:        ${stats['Total volume']:,.2f}"
    )

    # ========================================================
    # RISK
    # ========================================================

    lines.append("")
    lines.append("--- RISK ---")

    lines.append(
        f"Maximum drawdown:    ${max_dd:,.2f}"
    )

    # ========================================================
    # COIN
    # ========================================================

    lines.append("")
    lines.append("--- BY COIN ---")

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
    lines.append("--- LONG / SHORT ---")

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
    # DAILY
    # ========================================================

    lines.append("")
    lines.append("--- RECENT DAILY P&L ---")

    if not daily.empty:

        lines.append(
            daily.tail(20).to_string(
                float_format=lambda x:
                f"{x:,.2f}"
            )
        )

    else:

        lines.append(
            "No daily data."
        )

    lines.append("")
    lines.append(
        "=" * 70
    )

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\nConnecting to Hyperliquid..."
    )

    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    account = get_account_state()

    fills = get_fills()

    funding = get_funding()

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
    # DEBUG CHECK
    # --------------------------------------------------------

    print("\n")
    print("=" * 70)
    print("P&L / FEE CHECK")
    print("=" * 70)

    print(
        f"Closed P&L:          "
        f"${fills['closedPnl'].sum():,.2f}"
    )

    print(
        f"Fee cost:            "
        f"${fills['feeCost'].sum():,.2f}"
    )

    print(
        f"NET TRADING P&L:     "
        f"${fills['netTradingPnl'].sum():,.2f}"
    )

    print("=" * 70)

    # --------------------------------------------------------
    # STATS
    # --------------------------------------------------------

    stats = calculate_stats(
        fills
    )

    daily = daily_pnl(
        fills,
        funding
    )

    coin_stats = pnl_by_coin(
        fills
    )

    direction_stats = (
        long_short_stats(
            fills
        )
    )

    max_dd = calculate_drawdown(
        daily
    )

    # --------------------------------------------------------
    # FUNDING
    # --------------------------------------------------------

    if (
        funding is not None
        and not funding.empty
    ):

        total_funding = (
            funding["fundingPnl"]
            .sum()
        )

    else:

        total_funding = 0.0

    # --------------------------------------------------------
    # REPORT
    # --------------------------------------------------------

    report = create_report(
        account=account,
        stats=stats,
        total_funding=total_funding,
        max_dd=max_dd,
        coin_stats=coin_stats,
        direction_stats=direction_stats,
        daily=daily
    )

    # --------------------------------------------------------
    # PRINT
    # --------------------------------------------------------

    print("")
    print(report)

    # --------------------------------------------------------
    # SAVE FILE
    # --------------------------------------------------------

    filename = (
        "hyperliquid_daily_report.txt"
    )

    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(report)

    print("")
    print(
        f"Report saved as {filename}"
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
