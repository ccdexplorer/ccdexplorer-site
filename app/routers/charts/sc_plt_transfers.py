import datetime as dt

import dateutil
import pandas as pd
import plotly.graph_objects as go
from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
import uuid
from typing import Any, Optional
from app.jinja2_helpers import templates
from app.routers.statistics import (
    ccdexplorer_plotly_template,
    get_all_data_for_analysis_limited,
)
from app.utils import get_url_from_api

router = APIRouter()


@router.get("/{net}/charts/plt-transfers", response_class=HTMLResponse)
async def get_plt_transfers(
    request: Request,
    net: str,
):
    if net == "mainnet":
        chain_start = dt.date(2025, 9, 22).strftime("%Y-%m-%d")
        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/plts/overview",
            request.app.httpx_client,
        )
        plts: dict = api_result.return_value if api_result.ok else {}  # type: ignore
        stablecoin_tracks = sorted(
            list(set([x["stablecoin_tracks"] for x in plts.values()]))
        )
        stablecoin_tracks = {x: x for x in stablecoin_tracks if x is not None}
        if "XAU" in stablecoin_tracks:
            stablecoin_tracks["XAU"] = "Gold"
        yesterday = (
            dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)
        ).strftime("%Y-%m-%d")
        filename = f"/tmp/plt-transfers - {dt.datetime.now():%Y-%m-%d %H-%M-%S} - {uuid.uuid4()}.csv"
        return templates.TemplateResponse(
            "charts/sc_plt_transfers.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "chain_start": chain_start,
                "yesterday": yesterday,
                "filename": filename,
                "include_dropdown_fancy": True,
                "dropdown_label": "PLTs that track",
                "dropdown_elements": stablecoin_tracks,
                "include_kpis": True,
                "kpi_elements": {
                    "tvl_in_usd": "TVL (in USD)",
                    "mint": "Mint",
                    "transfer": "Transfer",
                    "burn": "Burn",
                    "tx_count": "Transaction Count",
                },
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


def extract_usd_transfers(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for entry in data:
        date = entry["date"]
        tokens = entry["tokens"]
        simplified_tokens = {}
        for token_name, token_data in tokens.items():
            simplified_tokens[token_name] = {
                "USD.transfer": token_data["USD"]["transfer"],
                "USD.burn": token_data["USD"]["burn"],
                "USD.mint": token_data["USD"]["mint"],
                "USD.total_supply": token_data["USD"]["total_supply"],
                "count_txs": token_data["count_txs"],
            }
        result.append({"date": date, "tokens": simplified_tokens})
    return result


class PostData(BaseModel):
    theme: str
    start_date: str
    end_date: str
    group_by_selection: str
    trace_selection: Optional[str] = None
    dropdown_values_fancy: str
    kpi: Optional[str] = None
    filename: str


@router.post(
    "/{net}/ajax_statistics_standalone/plt_transfers",
    response_class=Response,
)
async def statistics_plt_transfers(
    request: Request,
    net: str,
    post_data: PostData,
):
    # theme = await get_theme_from_request(request)
    tracks = post_data.dropdown_values_fancy
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
    analysis = "statistics_plt"
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

    all_data = await get_all_data_for_analysis_limited(
        analysis, request.app, post_data.start_date, post_data.end_date
    )

    df_per_day = pd.json_normalize(extract_usd_transfers(all_data)).fillna(0)  # type: ignore

    df_per_day["date"] = pd.to_datetime(df_per_day["date"])
    agg_map = {
        col: ("last" if "USD.total_supply" in col else "sum")
        for col in df_per_day.columns
        if col != "date"
    }

    df_per_day = (
        df_per_day.groupby(
            [pd.Grouper(key="date", axis=0, freq=letter, label="left", closed="left")]  # type: ignore
        )
        .agg(agg_map)
        .reset_index()
    )
    fig = go.Figure()

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/plts/overview",
        request.app.httpx_client,
    )
    plts: dict = api_result.return_value if api_result.ok else {}  # type: ignore

    for plt in plts.values():
        if plt["stablecoin_tracks"] == tracks:
            if post_data.kpi in ["mint", "transfer", "burn"]:
                title = f"{post_data.kpi.capitalize()} for stablecoins tracking {tracks} (in USD)"
                fig.add_trace(
                    go.Bar(
                        x=df_per_day["date"].to_list(),
                        y=df_per_day[
                            f"tokens.{plt['_id']}.USD.{post_data.kpi}"
                        ].to_list(),
                        name=f"{plt['_id']}",
                        # marker=dict(color="#549FF2"),
                    )
                )
            if post_data.kpi == "tx_count":
                title = f"Tx count for stablecoins tracking {tracks}"
                fig.add_trace(
                    go.Bar(
                        x=df_per_day["date"].to_list(),
                        y=df_per_day[f"tokens.{plt['_id']}.count_txs"].to_list(),  # type: ignore
                        name=f"{plt['_id']}",
                        # marker=dict(color="#549FF2"),
                    )
                )
            if post_data.kpi == "tvl_in_usd":
                title = (
                    f"TVL (end of period) for stablecoins tracking {tracks} (in USD)"
                )
                fig.add_trace(
                    go.Bar(
                        x=df_per_day["date"].to_list(),
                        y=df_per_day[f"tokens.{plt['_id']}.USD.total_supply"].to_list(),  # type: ignore
                        name=f"{plt['_id']}",
                        # marker=dict(color="#549FF2"),
                    )
                )
    fig.update_xaxes(type="date")

    fig.update_layout(
        barmode="stack",
        showlegend=True,
        legend_orientation="h",
        legend_y=-0.2,
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
