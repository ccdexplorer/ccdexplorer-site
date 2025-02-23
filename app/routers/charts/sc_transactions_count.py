import datetime as dt

import dateutil
import pandas as pd
from typing import Optional
import plotly.graph_objects as go
from ccdexplorer_fundamentals.user_v2 import UserV2
from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_AccountTransactionEffects,
    CCD_RejectReason,
)
from pydantic import BaseModel
import uuid

from app.jinja2_helpers import templates
from app.routers.statistics import (
    ccdexplorer_plotly_template,
    get_all_data_for_analysis_limited,
)
from app.state import get_user_detailsv2
from app.utils import get_url_from_api

router = APIRouter()


@router.get("/{net}/charts/transactions-count", response_class=HTMLResponse)
async def get_sc_transactions_count(
    request: Request,
    net: str,
):
    user: UserV2 = await get_user_detailsv2(request)
    chain_start = dt.date(2021, 6, 9).strftime("%Y-%m-%d")
    yesterday = (dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )

    dropdown_elements = [
        "account",
        "staking",
        "smart ctr",
        "transfer",
        "register data",
    ]
    filename = f"/tmp/transactions-types - {dt.datetime.now():%Y-%m-%d %H-%M-%S} - {uuid.uuid4()}.csv"
    return templates.TemplateResponse(
        "charts/sc_transactions_count.html",
        {
            "request": request,
            "env": request.app.env,
            "user": user,
            "net": net,
            "chain_start": chain_start,
            "yesterday": yesterday,
            "dropdown_elements": dropdown_elements,
            "filename": filename,
        },
    )


class TXCountReportingRequest(BaseModel):
    # net: str
    theme: str
    start_date: str
    end_date: str
    group_by_selection: str
    trace_selection: str
    filename: str


@router.post(
    "/{net}/ajax_transaction_types_reporting",
    response_class=Response,
)
async def ajax_transaction_types_reporting(
    request: Request,
    net: str,
    post_data: TXCountReportingRequest,
):
    post_data.trace_selection = post_data.trace_selection.split(",")
    theme = post_data.theme
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    start_date_str = post_data.start_date
    end_date_str = post_data.end_date
    parsed_date: dt.datetime = dateutil.parser.parse(post_data.start_date)
    post_data.start_date = dt.datetime(parsed_date.year, parsed_date.month, 1).strftime(
        "%Y-%m-%d"
    )

    end_parsed: dt.datetime = dateutil.parser.parse(post_data.end_date)
    next_month = dt.datetime(end_parsed.year, end_parsed.month, 1) + relativedelta(
        months=1
    )
    last_day = next_month - relativedelta(days=1)
    post_data.end_date = last_day.strftime("%Y-%m-%d")
    analysis = "statistics_mongo_transactions"

    if post_data.group_by_selection == "daily":
        letter = "D"
        tooltip = "Day"
    if post_data.group_by_selection == "weekly":
        letter = "W-MON"
        tooltip = "Week"
    if post_data.group_by_selection == "monthly":
        letter = "MS"
        tooltip = "Month"

    all_data = await get_all_data_for_analysis_limited(
        analysis, request.app, post_data.start_date, post_data.end_date
    )
    df = pd.json_normalize(all_data)
    df.fillna(0)
    df["date"] = pd.to_datetime(df["date"])
    df = (
        df.groupby(
            [pd.Grouper(key="date", axis=0, freq=letter, label="left", closed="left")]
        )
        .sum()
        .reset_index()
    )

    # only continue if we have data
    if len(df) > 0:
        # make sure we can sum up values
        df.fillna(0)
        df["date"] = pd.to_datetime(df["date"])
        df = df.fillna(0)

        # Account
        df = add_if_present(
            "account",
            ["account_creation", "credential_keys_updated", "credentials_updated"],
            df,
        )

        # Staking
        df = add_if_present(
            "staking",
            [
                "baker_configured",
                "baker_added",
                "baker_removed",
                "baker_keys_updated",
                "baker_restake_earnings_updated",
                "baker_stake_updated",
                "delegation_configured",
            ],
            df,
        )

        # Smart Contracts
        df = add_if_present(
            "smart ctr",
            ["contract_initialized", "contract_update_issued", "module_deployed"],
            df,
        )

        # Data
        df = add_if_present("register data", ["data_registered"], df)

        # Transfer
        df = add_if_present(
            "transfer",
            [
                "account_transfer",
                "transferred_to_encrypted",
                "transferred_to_public",
                "encrypted_amount_transferred",
                "transferred_with_schedule",
            ],
            df,
        )

        fig = go.Figure()
        if "account" in post_data.trace_selection:
            fig.add_trace(
                go.Bar(
                    x=df["date"].to_list(),
                    y=df["account"].to_list(),
                    name="Account",
                    marker=dict(color="#EE9B54"),
                )
            )
        if "transfer" in post_data.trace_selection:
            fig.add_trace(
                go.Bar(
                    x=df["date"].to_list(),
                    y=df["transfer"].to_list(),
                    name="Transfer",
                    marker=dict(color="#F7D30A"),
                )
            )

        if "smart ctr" in post_data.trace_selection:
            fig.add_trace(
                go.Bar(
                    x=df["date"].to_list(),
                    y=df["smart ctr"].to_list(),
                    name="Smart Contracts",
                    marker=dict(color="#6E97F7"),
                )
            )

        if "staking" in post_data.trace_selection:
            fig.add_trace(
                go.Bar(
                    x=df["date"].to_list(),
                    y=df["staking"].to_list(),
                    name="Staking",
                    marker=dict(color="#F36F85"),
                )
            )

        if "register data" in post_data.trace_selection:
            fig.add_trace(
                go.Bar(
                    x=df["date"].to_list(),
                    y=df["register data"].to_list(),
                    name="Data",
                    marker=dict(color="#AE7CF7"),
                )
            )

        title = "Account Transaction Types"
        trace_titles = {
            "account": "Account",
            "transfer": "Transfer",
            "smart ctr": "Smart Contracts",
            "staking": "Staking",
            "register data": "Data",
        }
        # Generate title based on selected traces
        selected_traces = post_data.trace_selection

        selected_titles = [
            trace_titles[trace] for trace in selected_traces if trace in trace_titles
        ]

        title = (
            f"Account Transaction Types ({', '.join(selected_titles)}) per {tooltip}"
        )

        fig.update_layout(
            barmode="stack",
            showlegend=False,
            title=f"<b>{title}</b><br><sup>{start_date_str} - {end_date_str}</sup>",
            template=ccdexplorer_plotly_template(theme),
            height=400,
        )

        df = df[["date"] + post_data.trace_selection]
        df["total_selected"] = df[post_data.trace_selection].sum(axis=1)
        df.to_csv(post_data.filename, index=False)
        return fig.to_html(
            config={"responsive": True, "displayModeBar": False},
            full_html=False,
            include_plotlyjs=False,
        )


def add_if_present(grouper_name: str, column_names: list[str], df: pd.DataFrame):
    for column_name in column_names:
        if column_name in df.columns:
            if grouper_name not in df.columns:
                df[grouper_name] = 0
            df[grouper_name] += df[column_name]
    return df


class PostData(BaseModel):
    theme: str
    start_date: str
    end_date: str
    group_by_selection: str
    trace_selection: str


@router.post(
    "/{net}/ajax_statistics_standalone/statistics_network_summary_accounts_per_day",
    response_class=Response,
)
async def statistics_network_summary_accounts_per_day_standalone(
    request: Request,
    net: str,
    post_data: PostData,
):
    # theme = await get_theme_from_request(request)
    theme = post_data.theme
    start_date_str = post_data.start_date
    end_date_str = post_data.end_date
    parsed_date: dt.datetime = dateutil.parser.parse(post_data.start_date)
    post_data.start_date = dt.datetime(parsed_date.year, parsed_date.month, 1).strftime(
        "%Y-%m-%d"
    )

    end_parsed: dt.datetime = dateutil.parser.parse(post_data.end_date)
    next_month = dt.datetime(end_parsed.year, end_parsed.month, 1) + relativedelta(
        months=1
    )
    last_day = next_month - relativedelta(days=1)
    post_data.end_date = last_day.strftime("%Y-%m-%d")
    analysis = "statistics_network_summary"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    if post_data.group_by_selection == "daily":
        letter = "D"
        tooltip = "Day"
    if post_data.group_by_selection == "weekly":
        letter = "W"
        tooltip = "Week"
    if post_data.group_by_selection == "monthly":
        letter = "ME"
        tooltip = "Month"

    if post_data.trace_selection != "cis5":

        all_data = await get_all_data_for_analysis_limited(
            analysis, request.app, post_data.start_date, post_data.end_date
        )

        df_per_day = pd.DataFrame(all_data)
        df_per_day["d_count_accounts"] = df_per_day["account_count"] - df_per_day[
            "account_count"
        ].shift(+1)

        df_per_day = df_per_day.dropna()

        df_per_day.rename(
            columns={"d_count_accounts": "growth_native", "account_count": "level"},
            inplace=True,
        )
        df_per_day = df_per_day[["date", "growth_native"]]

    if post_data.trace_selection != "native":
        ###CIS-5 public keys
        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/mainnet/smart-wallets/public-key-creation/{post_data.start_date}/{post_data.end_date}",
            request.app.httpx_client,
        )
        result = api_result.return_value if api_result.ok else []
        if len(result) == 0:
            df_cis5 = pd.DataFrame(columns=["date", "growth_cis5"])
        else:
            df_cis5 = pd.DataFrame(result)
            df_cis5.rename(
                columns={"_id": "date", "count": "growth_cis5"},
                inplace=True,
            )
    if post_data.trace_selection == "all":
        if len(df_cis5) > 0:
            df_merged = pd.merge(df_per_day, df_cis5, on="date", how="outer").fillna(0)
        else:
            df_merged = df_per_day
    elif post_data.trace_selection == "native":
        df_merged = df_per_day
    elif post_data.trace_selection == "cis5":
        df_merged = df_cis5

    df_merged["date"] = pd.to_datetime(df_merged["date"])
    df_merged = (
        df_merged.groupby([pd.Grouper(key="date", axis=0, freq=letter)])
        .sum()
        .reset_index()
    )
    fig = go.Figure()
    if post_data.trace_selection != "cis5":
        fig.add_trace(
            go.Bar(
                x=df_merged["date"].to_list(),
                y=df_merged["growth_native"].to_list(),
                name="Native",
                marker=dict(color="#549FF2"),
            )
        )
    if post_data.trace_selection != "native":
        if "growth_cis5" in df_merged.columns:
            fig.add_trace(
                go.Bar(
                    x=df_merged["date"].to_list(),
                    y=df_merged["growth_cis5"].to_list(),
                    name="CIS-5",
                    marker=dict(color="#AE7CF7"),
                )
            )

    fig.update_xaxes(type="date")
    if post_data.trace_selection == "all":
        title = f"Accounts (Native and CIS-5) Growth per {tooltip}"
    if post_data.trace_selection == "native":
        title = f"Accounts (Native) Growth per {tooltip}"
    if post_data.trace_selection == "cis5":
        title = f"Accounts (CIS-5) Growth per {tooltip}"

    fig.update_layout(
        barmode="stack",
        showlegend=False,
        title=f"<b>{title}</b><br><sup>{start_date_str} - {end_date_str}</sup>",
        template=ccdexplorer_plotly_template(theme),
        height=400,
    )

    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )
