import datetime as dt

import dateutil
import httpx
import plotly.express as px
import plotly.graph_objects as go
import polars as polars
from ccdexplorer_fundamentals.credential import Identity
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_AccountInfo,
    CCD_BlockItemSummary,
    CCD_PoolInfo,
)
import math
from ccdexplorer_fundamentals.user_v2 import UserV2
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from plotly.subplots import make_subplots

from app.classes.dressingroom import (
    MakeUp,
    MakeUpRequest,
    RequestingRoute,
)
from app.env import environment
from app.jinja2_helpers import templates
from app.state import get_httpx_client, get_labeled_accounts, get_user_detailsv2
from app.utils import (
    PaginationRequest,
    account_link,
    calculate_skip,
    ccdexplorer_plotly_template,
    get_url_from_api,
    pagination_calculator,
    verbose_timedelta,
    create_dict_for_tabulator_display,
)

router = APIRouter()


@router.post("/{net}/account/inactive/{validator_id}", response_class=Response)
async def account_validator_inactive(
    request: Request,
    net: str,
    validator_id: str,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
    tags: dict = Depends(get_labeled_accounts),
):
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{validator_id}/validator-inactive",
        httpx_client,
    )
    result = api_result.return_value if api_result.ok else None
    if not result:
        return None

    html = templates.get_template(
        "account/account_validator_inactive_messages.html"
    ).render({"result": result})

    return html


@router.post(
    "/{net}/account/baker-performance/{validator_id}/{days}", response_class=Response
)
async def account_baker_performance_graph(
    request: Request,
    net: str,
    validator_id: str,
    days: int,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
    tags: dict = Depends(get_labeled_accounts),
):
    theme = "dark"
    body = await request.body()
    if body:
        theme = body.decode("utf-8").split("=")[1]
    if net == "mainnet":
        show_x_number_of_days = days
        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/account/{validator_id}/validator-performance",
            httpx_client,
        )
        result = api_result.return_value if api_result.ok else None

        if not result:
            return None

        df_source = polars.json_normalize(result)
        df = df_source.clone().tail(show_x_number_of_days)

        # period_string = (
        #     "all data"
        #     if df.height() == df_source.height()
        #     else f"last {show_x_number_of_days:,.0f} days"
        # )

        # Step 3: Calculate cumulative sums for specific columns
        df = df.with_columns(
            [
                polars.col("pool_status.current_payday_info.blocks_baked")
                .cum_sum()
                .alias("Sum (actually baked)"),
                polars.col("expectation").cum_sum().alias("Sum (expectation)"),
            ]
        )

        df = df.select(["date", "Sum (actually baked)", "Sum (expectation)"])

        df = df.rename(
            {
                "Sum (actually baked)": "Sum (validated)",
                "Sum (expectation)": "Sum (expectation)",
            }
        )

        df_cumsum = df.melt(
            id_vars="date",  # Identifier column
            value_vars=["Sum (validated)", "Sum (expectation)"],  # Columns to melt
            variable_name="var",  # Name for the variable column
            value_name="value",  # Name for the value column
        )

        f_actual = df_cumsum.filter(polars.col("var") == "Sum (validated)")
        f_expect = df_cumsum.filter(polars.col("var") == "Sum (expectation)")
        rng = ["#70B785", "#AE7CF7"]

        # Create figure with secondary y-axis
        fig = make_subplots()
        fig.add_trace(
            go.Scatter(
                x=list(f_actual.get_column("date")),
                y=list(f_actual.get_column("value")),
                fill="tozeroy",
                name="Sum (validated)",
                marker=dict(color="#70B785"),
            ),
            secondary_y=False,
        )

        fig.add_trace(
            go.Scatter(
                x=list(f_expect.get_column("date")),
                y=list(f_expect.get_column("value")),
                name="Sum (expectation)",
                marker=dict(color="#AE7CF7"),
            ),
            secondary_y=False,
            # showgrid=False,
        )

        fig.update_xaxes(type="date")
        fig.update_layout(
            showlegend=True,
            legend_y=-0.2,
            legend=dict(orientation="h"),
            # title=dict(
            # text="Validator Performance",
            # subtitle=dict(
            #     text=f"Validator {validator_id}",
            #     # font=dict(color="gray", size=13),
            # ),),
            title=f"<b>Validator Performance</b><br><sup>Validator {validator_id}</sup>",
            template=ccdexplorer_plotly_template(theme),
            height=250,
            margin=dict(l=0, r=0, t=0, b=0),
        )
        return fig.to_html(
            config={"responsive": True, "displayModeBar": False},
            full_html=False,
            include_plotlyjs=False,
        )

    else:
        return ""


@router.get("/{net}/account/{index}/earliest-win-time", response_class=HTMLResponse)
async def get_account_earliest(
    request: Request,
    net: str,
    index: int,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    request.state.api_calls = {}
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{index}/earliest-win-time",
        httpx_client,
    )
    earliest_win_time = api_result.return_value if api_result.ok else None
    if not earliest_win_time:
        error = f"Can't get earliest win time for validator {index} on {net}."
        return templates.TemplateResponse(
            "base/error-request.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )

    earliest_win_time = dateutil.parser.parse(earliest_win_time)
    now = dt.datetime.now().astimezone(tz=dt.timezone.utc)
    if now < earliest_win_time:
        return verbose_timedelta(earliest_win_time - now)
    else:
        return "0 sec"


@router.get(
    "/{net}/account/{account_address}/aliases-in-use", response_class=HTMLResponse
)
async def get_account_aliases_in_use(
    request: Request,
    net: str,
    account_address: str,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    request.state.api_calls = {}
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{account_address}/aliases-in-use",
        httpx_client,
    )
    aliases_in_use = api_result.return_value if api_result.ok else []
    if len(aliases_in_use) > 0:
        html = templates.get_template("account/account_aliases_in_use.html").render(
            {
                "aliases_in_use": aliases_in_use,
                "net": net,
                "account_address": account_address,
                "request": request,
            }
        )

        return html
    else:
        return ""


@router.get(
    "/{net}/account/{validator_id}/staking-rewards-object", response_class=HTMLResponse
)
async def get_validator_pool_apy_rewards(
    request: Request,
    net: str,
    validator_id: int,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    request.state.api_calls = {}
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{validator_id}/staking-rewards-object",
        httpx_client,
    )
    pool_apy_object = api_result.return_value if api_result.ok else None
    if pool_apy_object:
        html = templates.get_template("account/account_delegator_rewards.html").render(
            {
                "pool_apy_object": pool_apy_object,
            }
        )

        return html
    else:
        return ""


@router.get("/{net}/account/{index}/current-payday-stats", response_class=HTMLResponse)
async def get_account_payday_stats(
    request: Request,
    net: str,
    index: int,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    request.state.api_calls = {}
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{index}/current-payday-stats",
        httpx_client,
    )
    stats = api_result.return_value if api_result.ok else None

    if not stats:
        error = f"Can't get current payday stats for validator {index} on {net}."
        return templates.TemplateResponse(
            "base/error-request.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )
    else:
        return stats


@router.get(
    "/account_validator_transactions/{net}/{account_id}",
    response_class=HTMLResponse,
)
async def get_account_validator_transactions(
    request: Request,
    net: str,
    account_id: str,
    page: int = Query(),
    size: int = Query(),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
    # recurring: Recurring = Depends(get_recurring),
    tags: dict = Depends(get_labeled_accounts),
):
    """
    Add {net}.
    """
    user: UserV2 | None = await get_user_detailsv2(request)

    skip = (page - 1) * size
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{account_id}/validator-transactions/{skip}/{size}",
        httpx_client,
    )
    tx_result = api_result.return_value if api_result.ok else None

    if not tx_result:
        error = f"Request error getting validator transactions for account at {account_id} on {net}."
        return templates.TemplateResponse(
            "base/error-request.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )

    tx_result_transactions = tx_result["transactions"]
    total_rows = tx_result["total_tx_count"]
    last_page = math.ceil(total_rows / size)
    tb_made_up_txs = []
    if len(tx_result_transactions) > 0:
        for transaction in tx_result_transactions:
            transaction = CCD_BlockItemSummary(**transaction)
            makeup_request = MakeUpRequest(
                **{
                    "net": net,
                    "httpx_client": httpx_client,
                    "tags": tags,
                    "user": user,
                    "app": request.app,
                    "requesting_route": RequestingRoute.account,
                }
            )

            classified_tx = await MakeUp(
                makeup_request=makeup_request
            ).prepare_for_display(transaction, "", False)

            type_additional_info, sender = await classified_tx.transform_for_tabulator()

            dct = create_dict_for_tabulator_display(
                net, classified_tx, type_additional_info, sender
            )
            # {% set event=tx.events_list[0] %}
            # {{event.update|safe }}

            dct["first_event"] = (
                classified_tx.events_list[0].update
                if classified_tx.events_list
                else None
            )
            tb_made_up_txs.append(dct)
    return JSONResponse(
        {
            "data": tb_made_up_txs,
            "last_page": last_page,
            "last_row": total_rows,
        }
    )


@router.get(
    "/account/validator-tally/{net}/{account_id}",
    response_class=HTMLResponse,
)
async def get_validator_tally(
    request: Request,
    net: str,
    account_id: str,
    page: int = Query(),
    size: int = Query(),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
    # recurring: Recurring = Depends(get_recurring),
):

    skip = (page - 1) * size
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{account_id}/validator-tally/{skip}/{size}",
        httpx_client,
    )
    tally = api_result.return_value if api_result.ok else None
    if not tally:
        error = f"Request error getting validator tally for account at {account_id} on {net}."
        return templates.TemplateResponse(
            "base/error-request.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )

    tally_data = tally["data"]
    total_rows = tally["total_row_count"]  # type: ignore
    last_page = math.ceil(total_rows / size)

    return JSONResponse(
        {
            "data": tally_data,
            "last_page": last_page,
            "last_row": total_rows,
        }
    )
