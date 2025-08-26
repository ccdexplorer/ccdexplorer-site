import math

import httpx
import plotly.graph_objects as go
import polars as polars
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_DelegatorInfo,
    CCD_DelegatorRewardPeriodInfo,
)
from ccdexplorer_fundamentals.user_v2 import UserV2
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from plotly.subplots import make_subplots

from app.env import environment
from app.jinja2_helpers import templates
from app.state import get_httpx_client, get_labeled_accounts, get_user_detailsv2
from app.utils import (
    account_link,
    ccdexplorer_plotly_template,
    from_address_to_index,
    get_url_from_api,
)

router = APIRouter()


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
    return stats


def prepare_delegators_data(
    new_delegators, delegators, delegators_in_block_dict, request
):
    """
    Prepare delegator entries for Tabulator with only account_index, stake, and message.


    """
    rows = []

    # New delegators
    for account_id, value in new_delegators.items():
        rows.append(
            {
                "account_index": from_address_to_index(
                    account_id[:29], "mainnet", request.app
                ),
                "stake": value.get("stake"),
                "message": "(to be included <br/>in next payday)",
            }
        )

        # pending = value.get("pending_change", {}) or {}
        # # Construct message
        # messages = []
        # if pending.get("remove"):
        #     messages.append(f"Delegation to be removed at: {pending['remove']}")
        # if pending.get("reduce"):
        #     reduce_info = pending["reduce"]
        #     messages.append(
        #         f"Delegation stake reduced to: {reduce_info.get('new_stake')} at: {reduce_info.get('effective_time')}"
        #     )
        # message = "; ".join(messages)

        # rows.append(
        #     {
        #         "account_index": from_address_to_index(
        #             account_id[:29], "mainnet", request.app
        #         ),
        #         "stake": value.get("stake"),
        #         "message": message,
        #     }
        # )

    # Current delegators
    for row in delegators:
        pending_block = (
            delegators_in_block_dict.get(row.get("account"), {}).get(
                "pending_change", {}
            )
            or {}
        )
        messages = []
        if pending_block.get("remove"):
            messages.append(f"Delegation to be removed at: {pending_block['remove']}")
        if pending_block.get("reduce"):
            reduce_info = pending_block["reduce"]
            messages.append(
                f"Delegation stake reduced to: {reduce_info.get('new_stake')} at: {reduce_info.get('effective_time')}"
            )
        message = "; ".join(messages)

        rows.append(
            {
                "account_index": row.get("account"),
                "stake": row.get("stake"),
                "message": message,
            }
        )

    return rows


@router.get(
    "/account_pool_delegators/{net}/{account_index}",
    response_class=HTMLResponse,
)
async def get_account_pool_delegators(
    request: Request,
    net: str,
    account_index: int,
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
        f"{request.app.api_url}/v2/{net}/account/{account_index}/pool/delegators/{skip}/{size}",
        httpx_client,
    )
    delegator_dict = api_result.return_value if api_result.ok else None
    if not delegator_dict:
        error = f"Request error getting pool delegators for account at {account_index} on {net}."
        return templates.TemplateResponse(
            "base/error-request.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )

    delegators = delegator_dict["delegators"]

    delegators_in_block = delegator_dict["delegators_in_block"]
    delegators_in_dict = {
        CCD_DelegatorInfo(**x).account: x for x in delegators_in_block
    }
    delegators_current_payday = delegator_dict["delegators_current_payday"]
    new_delegators = delegator_dict["new_delegators"]
    new_delegators_dict = {x: delegators_in_dict[x] for x in new_delegators}
    total_rows = delegator_dict["total_delegators"]

    delegators_current_payday_dict = {
        CCD_DelegatorRewardPeriodInfo(**x).account: x for x in delegators_current_payday
    }
    delegators_in_block_dict = {
        CCD_DelegatorInfo(**x).account: x for x in delegators_in_block
    }

    delegators_with_ids = delegators

    delegators = []
    for dele in delegators_with_ids:
        # if dele["account"][:29] in account_ids_to_lookup:
        dele.update(
            {"account": from_address_to_index(dele["account"][:29], net, request.app)}
        )
        delegators.append(dele)

    # delegators = [
    #     x.update({"account": account_ids_to_lookup.get(x["account"], x["account"])})
    #     for x in delegators_with_ids
    # ]
    # combined_delegators = []
    # for account_id, value in new_delegators_dict.items():

    combined_delegators = prepare_delegators_data(
        new_delegators_dict, delegators, delegators_in_block_dict, request
    )
    total_rows = total_rows + len(new_delegators_dict)
    made_up_delegators = []
    for d in combined_delegators:
        made_up_delegator = {}
        made_up_delegator["account"] = account_link(
            d["account_index"],
            "mainnet",
            user=user,
            tags=tags,
            app=request.app,
        )

        made_up_delegator["staked_amount"] = d["stake"]
        made_up_delegator["message"] = d["message"]
        # download
        made_up_delegator["account_download"] = d["account_index"]
        made_up_delegators.append(made_up_delegator)

    last_page = math.ceil(total_rows / size)
    return JSONResponse(
        {
            "data": made_up_delegators,
            "last_page": max(1, last_page),
            "last_row": total_rows,
        }
    )

    # html = templates.get_template("account/account_pool_delegators.html").render(
    #     {
    #         "delegators": delegators,
    #         "tags": tags,
    #         "user": user,
    #         "net": net,
    #         "request": request,
    #         "pagination": pagination,
    #         "totals_in_pagination": True,
    #         "total_rows": total_rows,
    # "new_delegators": new_delegators_dict,
    # "delegators_current_payday_dict": delegators_current_payday_dict,
    # "delegators_in_block_dict": delegators_in_block_dict,
    #     }
    # )

    # return html
