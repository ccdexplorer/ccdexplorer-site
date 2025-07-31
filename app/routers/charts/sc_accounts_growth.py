import datetime as dt

import dateutil
import pandas as pd
import plotly.graph_objects as go
from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
import uuid
from app.jinja2_helpers import templates
from app.routers.statistics import (
    ccdexplorer_plotly_template,
    get_all_data_for_analysis_limited,
)
from app.utils import get_url_from_api

router = APIRouter()


@router.get("/{net}/charts/accounts-growth", response_class=HTMLResponse)
async def get_accounts_growth(
    request: Request,
    net: str,
):
    if net == "mainnet":
        chain_start = dt.date(2021, 6, 9).strftime("%Y-%m-%d")
        yesterday = (
            dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)
        ).strftime("%Y-%m-%d")
        filename = f"/tmp/accounts-growth - {dt.datetime.now():%Y-%m-%d %H-%M-%S} - {uuid.uuid4()}.csv"
        return templates.TemplateResponse(
            "charts/sc_accounts_growth.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "chain_start": chain_start,
                "yesterday": yesterday,
                "filename": filename,
            },
        )
    else:
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )


class PostData(BaseModel):
    theme: str
    start_date: str
    end_date: str
    group_by_selection: str
    trace_selection: str
    filename: str


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
    post_data.trace_selection = post_data.trace_selection.split(",")
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
        letter = "W-MON"
        tooltip = "Week"
    if post_data.group_by_selection == "monthly":
        letter = "MS"
        tooltip = "Month"

    if "native" in post_data.trace_selection:

        all_data = await get_all_data_for_analysis_limited(
            analysis, request.app, post_data.start_date, post_data.end_date
        )

        df_per_day = pd.DataFrame(all_data)
        df_per_day["d_count_accounts"] = df_per_day["account_count"] - df_per_day[
            "account_count"
        ].shift(+1)

        df_per_day = df_per_day.dropna(subset=["d_count_accounts"])

        df_per_day.rename(
            columns={"d_count_accounts": "growth_native", "account_count": "level"},
            inplace=True,
        )
        df_per_day = df_per_day[["date", "growth_native"]]

    if "cis5" in post_data.trace_selection:
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
    if len(post_data.trace_selection) == 2:
        if len(df_cis5) > 0:
            df_merged = pd.merge(df_per_day, df_cis5, on="date", how="outer").fillna(0)
        else:
            df_merged = df_per_day
    elif post_data.trace_selection[0] == "native":
        df_merged = df_per_day
    elif post_data.trace_selection[0] == "cis5":
        df_merged = df_cis5

    df_merged["date"] = pd.to_datetime(df_merged["date"])
    df_merged = (
        df_merged.groupby(
            [pd.Grouper(key="date", axis=0, freq=letter, label="left", closed="left")]
        )
        .sum()
        .reset_index()
    )
    fig = go.Figure()
    if "native" in post_data.trace_selection:
        fig.add_trace(
            go.Bar(
                x=df_merged["date"].to_list(),
                y=df_merged["growth_native"].to_list(),
                name="Native",
                marker=dict(color="#549FF2"),
            )
        )
    if "cis5" in post_data.trace_selection:
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
    if len(post_data.trace_selection) == 2:
        title = f"Accounts (Native and CIS-5) Growth per {tooltip}"
    elif post_data.trace_selection[0] == "native":
        title = f"Accounts (Native) Growth per {tooltip}"
    elif post_data.trace_selection[0] == "cis5":
        title = f"Accounts (CIS-5) Growth per {tooltip}"

    fig.update_layout(
        barmode="stack",
        showlegend=False,
        title=f"<b>{title}</b><br><sup>{start_date_str} - {end_date_str}</sup>",
        template=ccdexplorer_plotly_template(theme),
        height=400,
    )

    # Convert non-date columns to integers
    non_date_columns = df_merged.columns.difference(["date"])
    # Fill NA values with 0
    df_merged = df_merged.fillna(0)
    df_merged[non_date_columns] = df_merged[non_date_columns].astype(int)

    df_merged.to_csv(post_data.filename, index=False)
    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )
