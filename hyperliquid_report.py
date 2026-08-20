import os
import requests
import pandas as pd
import numpy as np


# ============================================================
# CONFIG
# ============================================================

API_URL = "https://api.hyperliquid.xyz/info"

WALLET = os.environ["HYPERLIQUID_WALLET"]

HISTORY_FILE = "account_history.csv"
REPORT_FILE = "hyperliquid_daily_report.txt"


# ============================================================
# HYPERLIQUID API REQUEST
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
    # FEE COST
    # --------------------------------------------------------
    #
    # We treat the fee as a COST.
    #
    # abs() makes the displayed fee positive regardless
    # of whether Hyperliquid returns it as positive or negative.
    #
    # Example:
    #
    # API fee = -22.49
    #
    # feeCost = 22.49
    #
    # --------------------------------------------------------

    if "fee" in df.columns:

        df["feeCost"] = (
            df["fee"].abs()
        )

    else:

        df["feeCost"] = 0.0

    # --------------------------------------------------------
    # NET TRADING P&L
    # --------------------------------------------------------
    #
    # IMPORTANT:
    #
    # Closed P&L is the realised trading result.
    #
    # Fee is a COST.
    #
    # Therefore:
    #
    # Net Trading P&L =
    #
    # Closed P&L - ABS(Fee)
    #
    # Example:
    #
    # Closed P&L = +32.94
    # Fee        = -22.49
    #
    # Fee cost   = 22.49
    #
    # Net        = 10.45
    #
    # --------------------------------------------------------

    if (
        "closedPnl" in df.columns
        and "fee" in df.columns
    ):

        df["netTradingPnl"] = (
            df["closedPnl"] -
            df["fee"].abs()
        )

    else:

        df["netTradingPnl"] = 0.0

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

            df["date"] = (
                pd.to_datetime(
                    df["date"]
                )
                .dt
                .date
            )

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
    # PREVIOUS ACCOUNT VALUE
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
                previous_rows.iloc[-1][
                    "account_value"
                ]
            )

    # --------------------------------------------------------
    # ACTUAL DAILY ACCOUNT P&L
    # --------------------------------------------------------
    #
    # This is NOT reconstructed from fills.
    #
    # It is simply:
    #
    # Current account value
    # minus
    # Previous account value
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
    # REMOVE EXISTING TODAY
    # --------------------------------------------------------

    history = history[
        history["date"] != today
    ]

    # --------------------------------------------------------
    # ADD TODAY
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
    # SAVE
    # --------------------------------------------------------

    history.to_csv(
        HISTORY_FILE,
        index=False
    )

    return (
        history,
        previous_value,
        daily_pnl
    )


# ============================================================
# TODAY'S TRADING DATA
# ============================================================

def calculate_today_stats(
    fills,
    funding,
    today
):

    # --------------------------------------------------------
    # TODAY'S FILLS
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

        net_trading_pnl = (
            today_fills[
                "netTradingPnl"
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
        net_trading_pnl = 0.0
        volume = 0.0
        fills_count = 0

    # --------------------------------------------------------
    # TODAY'S FUNDING
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

        "net_trading_pnl": net_trading_pnl,

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

            "net_pnl": 0.0,

            "volume": 0.0,

            "winning_fills": 0,

            "losing_fills": 0,

            "win_rate": 0.0
        }

    closed = (
        fills[
            "closedPnl"
        ]
        .fillna(0)
    )

    fees = (
        fills[
            "feeCost"
        ]
        .fillna(0)
    )

    net_pnl = (
        fills[
            "netTradingPnl"
        ]
        .fillna(0)
    )

    # --------------------------------------------------------
    # WINNERS / LOSERS
    # --------------------------------------------------------

    winners = (
        net_pnl > 0
    ).sum()

    losers = (
        net_pnl < 0
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

        "net_pnl": net_pnl.sum(),

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

            NetTradingPnL=(
                "netTradingPnl",
                "sum"
            ),

            Volume=(
                "notional",
                "sum"
            )
        )

        .sort_values(
            "NetTradingPnL",
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

    return result


# ============================================================
# DAILY CLOSED P&L
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

    return daily.sort_index()


# ============================================================
# MAX ACCOUNT DRAWDOWN
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
    max_drawdown,
    coin_stats,
    direction_stats,
    daily_closed
):

    margin = (
        account[
            "marginSummary"
        ]
    )

    account_value = float(
        margin[
            "accountValue"
        ]
    )

    margin_used = float(
        margin[
            "totalMarginUsed"
        ]
    )

    position_notional = float(
        margin[
            "totalNtlPos"
        ]
    )

    withdrawable = float(
        account[
            "withdrawable"
        ]
    )

    today = (
        pd.Timestamp.now(
            tz="Europe/London"
        )
        .strftime(
            "%d %B %Y"
        )
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
        f"Net trading P&L:     ${today_stats['net_trading_pnl']:,.2f}"
    )

    lines.append(
        f"Funding:             ${today_stats['funding']:,.2f}"
    )

    lines.append(
        f"Volume:              ${today_stats['volume']:,.2f}"
    )

    # ========================================================
    # P&L RECONCILIATION
    # ========================================================

    lines.append("")
    lines.append(
        "--- P&L RECONCILIATION ---"
    )

    lines.append(
        f"Closed P&L:          ${today_stats['closed_pnl']:,.2f}"
    )

    lines.append(
        f"Trading fees:        -${today_stats['fees']:,.2f}"
    )

    lines.append(
        f"Net trading P&L:     ${today_stats['net_trading_pnl']:,.2f}"
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
    # ALL-TIME
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
        f"Net trading P&L:     ${fill_stats['net_pnl']:,.2f}"
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
    # ACCOUNT HISTORY
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

        history_display[
            "date"
        ] = (
            history_display[
                "date"
            ]
            .astype(str)
        )

        lines.append(
            history_display.to_string(
                index=False,
                float_format=lambda x:
                f"{x:,.2f}"
            )
        )

    else:

        lines.append(
            "No account history."
        )

    # ========================================================
    # DAILY CLOSED P&L
    # ========================================================

    lines.append("")
    lines.append(
        "--- RECENT DAILY P&L ---"
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

    else:

        lines.append(
            "No daily trading data."
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

    fills = (
        prepare_fills(
            fills
        )
    )

    funding = (
        prepare_funding(
            funding
        )
    )

    # ========================================================
    # RAW P&L / FEE DIAGNOSTIC
    # ========================================================

    print("")
    print(
        "=" * 70
    )
    print(
        "RAW P&L / FEE CHECK"
    )
    print(
        "=" * 70
    )

    if not fills.empty:

        diagnostic_columns = [
            col
            for col in [
                "coin",
                "side",
                "closedPnl",
                "fee",
                "feeCost",
                "netTradingPnl"
            ]
            if col in fills.columns
        ]

        print(
            fills[
                diagnostic_columns
            ]
            .tail(10)
            .to_string(
                index=False
            )
        )

        print("")
        print(
            f"SUM closedPnl:       "
            f"${fills['closedPnl'].sum():,.2f}"
        )

        print(
            f"SUM raw fee:         "
            f"${fills['fee'].sum():,.2f}"
        )

        print(
            f"SUM feeCost:         "
            f"${fills['feeCost'].sum():,.2f}"
        )

        print(
            f"SUM netTradingPnl:   "
            f"${fills['netTradingPnl'].sum():,.2f}"
        )

        print("")
        print(
            "EXPECTED CALCULATION:"
        )

        print(
            f"Closed P&L - Fee Cost = "
            f"${fills['closedPnl'].sum():,.2f} - "
            f"${fills['feeCost'].sum():,.2f} = "
            f"${fills['netTradingPnl'].sum():,.2f}"
        )

    else:

        print(
            "No fills returned."
        )

    print(
        "=" * 70
    )

    # --------------------------------------------------------
    # ACCOUNT VALUE
    # --------------------------------------------------------

    margin = (
        account[
            "marginSummary"
        ]
    )

    account_value = float(
        margin[
            "accountValue"
        ]
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
    # HISTORY
    # --------------------------------------------------------

    history = (
        load_history()
    )

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
    # ALL-TIME STATS
    # --------------------------------------------------------

    fill_stats = (
        calculate_fill_stats(
            fills
        )
    )

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
    # REPORT
    # --------------------------------------------------------

    report = create_report(

        account=account,

        today_stats=today_stats,

        fill_stats=fill_stats,

        history=history,

        previous_value=previous_value,

        daily_pnl=daily_pnl,

        max_drawdown=max_drawdown,

        coin_stats=coin_stats,

        direction_stats=direction_stats,

        daily_closed=daily_closed
    )

    # --------------------------------------------------------
    # PRINT
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
