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


@router.get("/{net}/charts/holders", response_class=HTMLResponse)
async def get_accounts_growth(
    request: Request,
    net: str,
):
    if net == "mainnet":
        chain_start = dt.date(2021, 6, 9).strftime("%Y-%m-%d")
        yesterday = (
            dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)
        ).strftime("%Y-%m-%d")
        filename = (
            f"/tmp/holders - {dt.datetime.now():%Y-%m-%d %H-%M-%S} - {uuid.uuid4()}.csv"
        )
        return templates.TemplateResponse(
            "charts/sc_holders.html",
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
    amount_chosen: str
    filename: str


@router.post(
    "/{net}/ajax_statistics_standalone/statistics_holders",
    response_class=Response,
)
async def statistics_holders(
    request: Request,
    net: str,
    post_data: PostData,
):
    # theme = await get_theme_from_request(request)
    # post_data.amount_chosen = post_data.trace_selection.split(",")  # type: ignore
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
    analysis = "statistics_daily_holders"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    all_data = await get_all_data_for_analysis_limited(
        analysis, request.app, post_data.start_date, post_data.end_date
    )

    df_per_day = pd.DataFrame(all_data)

    df_per_day["date"] = pd.to_datetime(df_per_day["date"])
    # df_merged = (
    #     df_per_day.groupby(
    #         [pd.Grouper(key="date", axis=0, freq=letter, label="left", closed="left")]
    #     )
    #     .sum()
    #     .reset_index()
    # )
    #     count_>=10000
    # 2529
    # count_>=20000
    # 2122
    # count_>=50000
    # 1588
    # count_>=100000
    # 1199
    # count_>=500000
    # 592
    # count_>=1000000
    # 385
    # count_>=2500000
    # 201
    # count_>=5000000
    # 144
    # count_>=10000000
    # 106
    # count_>=50000000
    # 47
    # count_>=100000000
    # 30
    if post_data.amount_chosen == "0":
        ss = "count_>=0"
    elif post_data.amount_chosen == "10K":
        ss = "count_>=10000"
    elif post_data.amount_chosen == "20K":
        ss = "count_>=20000"
    elif post_data.amount_chosen == "50K":
        ss = "count_>=50000"
    elif post_data.amount_chosen == "100K":
        ss = "count_>=100000"
    elif post_data.amount_chosen == "500K":
        ss = "count_>=500000"
    elif post_data.amount_chosen == "1M":
        ss = "count_>=1000000"
    elif post_data.amount_chosen == "2.5M":
        ss = "count_>=2500000"
    elif post_data.amount_chosen == "5M":
        ss = "count_>=5000000"
    elif post_data.amount_chosen == "10M":
        ss = "count_>=10000000"
    elif post_data.amount_chosen == "100M":
        ss = "count_>=100000000"
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=df_per_day["date"].to_list(),
            y=df_per_day[ss].to_list(),
            name="Native",
            marker=dict(color="#549FF2"),
        )
    )
    fig.update_xaxes(type="date")
    title = f"Daily Holders with account balance >= {post_data.amount_chosen} CCD"

    fig.update_layout(
        barmode="stack",
        showlegend=False,
        title=f"<b>{title}</b><br><sup>{start_date_str} - {end_date_str}</sup>",
        template=ccdexplorer_plotly_template(theme),
        height=400,
    )

    # Convert non-date columns to integers
    non_date_columns = df_per_day.columns.difference(["date"])
    # Fill NA values with 0
    df_per_day = df_per_day.fillna(0)
    df_per_day[non_date_columns] = df_per_day[non_date_columns].astype(int)

    df_per_day.to_csv(post_data.filename, index=False)
    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )
