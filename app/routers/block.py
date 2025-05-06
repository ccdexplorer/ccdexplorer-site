# ruff: noqa: F403, F405, E402, E501, E722

import httpx
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import CCD_BlockInfo
from ccdexplorer_fundamentals.mongodb import *
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse

from app.classes.dressingroom import (
    MakeUp,
    MakeUpRequest,
    RequestingRoute,
)
from app.env import *
from app.jinja2_helpers import *
from app.state import get_httpx_client, get_labeled_accounts, get_user_detailsv2

router = APIRouter()


@router.get("/{net}/block/{height_or_hash}", response_class=HTMLResponse)
async def request_block(
    request: Request,
    net: str,
    height_or_hash: int | str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    request.state.api_calls = {}
    user: UserV2 = await get_user_detailsv2(request)

    try:
        height_or_hash = int(height_or_hash)
    except ValueError:
        pass
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/block/{height_or_hash}",
        httpx_client,
    )
    block_info = CCD_BlockInfo(**api_result.return_value) if api_result.ok else None

    if not block_info:
        error = f"Can't find the block at {height_or_hash} on {net}."
        return templates.TemplateResponse(
            "base/error.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/block/{height_or_hash}/payday",
        httpx_client,
    )
    payday_info = api_result.return_value if api_result.ok else None

    if not payday_info:
        error = f"Request error for block at {height_or_hash} on {net}."
        return templates.TemplateResponse(
            "base/error.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )
    request.state.api_calls["Block Info"] = (
        f"{request.app.api_url}/docs#/Block/get_block_at_height_from_grpc_v2__net__block__height_or_hash__get"
    )
    request.state.api_calls["Chain Parameters"] = (
        f"{request.app.api_url}/docs#/Block/get_block_chain_parameters_v2__net__block__height__chain_parameters_get"
    )
    request.state.api_calls["Special Events"] = (
        f"{request.app.api_url}/docs#/Block/get_block_special_events_v2__net__block__height__special_events_get"
    )
    request.state.api_calls["Transactions"] = (
        f"{request.app.api_url}/docs#/Block/get_block_txs_v2__net__block__height__transactions__skip___limit__get"
    )
    request.state.api_calls["Payday Yes/No"] = (
        f"{request.app.api_url}/docs#/Block/get_block_payday_true_false_v2__net__block__height_or_hash__payday_get"
    )
    if payday_info["is_payday"]:
        request.state.api_calls["Payday Pool Rewards"] = (
            f"{request.app.api_url}/docs#/Block/get_block_payday_pool_rewards_v2__net__block__height__payday_pool_rewards__skip___limit__get"
        )
        request.state.api_calls["Payday Account Rewards"] = (
            f"{request.app.api_url}/docs#/Block/get_block_payday_account_rewards_v2__net__block__height__payday_account_rewards__skip___limit__get"
        )

    return templates.TemplateResponse(
        "block/block.html",
        {
            "request": request,
            "env": request.app.env,
            "payday_info": payday_info,
            # "baker_nodes": recurring.baker_nodes_by_baker_id,
            # "non_baker_nodes": recurring.non_baker_nodes_by_node_id,
            # "old": False,
            "net": net,
            "block_info": block_info,
            "user": user,
            "tags": tags,
        },
    )


@router.get(
    "/ajax_chain_parameters_html_v2/{net}/{height}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_chain_parameters_html_v2(
    request: Request,
    net: str,
    height: int,
    api_key: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    """
    Add {net}.
    """
    user: UserV2 = await get_user_detailsv2(request)

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/block/{height}/chain-parameters",
        httpx_client,
    )
    chain_parameters = api_result.return_value if api_result.ok else None
    if not chain_parameters:
        error = (
            f"Request error getting chain parameters for block at {height} on {net}."
        )
        return templates.TemplateResponse(
            "base/error-request.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )
    html = templates.get_template("/block/block_chain_parameters.html").render(
        {
            "cp": chain_parameters,
            "user": user,
            "tags": tags,
            "net": net,
            "request": request,
            # "net_postfix": net_postfix,
        }
    )

    return html


@router.get(
    "/ajax_special_events_html_v2/{net}/{height}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_special_events_html_v2(
    request: Request,
    net: str,
    height: int,
    api_key: str,
    # recurring: Recurring = Depends(get_recurring),
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/block/{height}/special-events",
        httpx_client,
    )
    special_events = api_result.return_value if api_result.ok else None

    if not isinstance(special_events, list):
        error = f"Request error getting special events for block at {height} on {net}."
        return templates.TemplateResponse(
            "base/error-request.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )

    primed = [
        x for x in special_events if x["validator_primed_for_suspension"] is not None
    ]
    suspended = [x for x in special_events if x["validator_suspended"] is not None]
    html = templates.get_template("/block/block_special_events.html").render(
        {
            "se": special_events,
            "user": user,
            "tags": tags,
            "net": net,
            # "baker_nodes": recurring.baker_nodes_by_baker_id,
            "request": request,
            "primed": primed,
            "suspended": suspended,
        }
    )

    return html


@router.get(
    "/ajax_payday_account_rewards_html_v2/{block_height}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_payday_account_rewards_html_v2(
    request: Request,
    block_height: int,
    requested_page: int,
    total_rows: int,
    api_key: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    limit = 30
    user: UserV2 = await get_user_detailsv2(request)
    if request.app.env["NET"] == "mainnet":
        skip = calculate_skip(requested_page, total_rows, limit)
        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/mainnet/block/{block_height}/payday/account-rewards/{skip}/{limit}",
            httpx_client,
        )
        account_rewards = api_result.return_value if api_result.ok else None
        if not account_rewards:
            error = f"Request error getting account rewards for block at {block_height} on mainnet."
            return templates.TemplateResponse(
                "base/error-request.html",
                {
                    "request": request,
                    "error": error,
                    "env": environment,
                    "net": "mainnet",
                },
            )

        pagination_request = PaginationRequest(
            total_txs=total_rows,
            requested_page=requested_page,
            word="account-reward",
            action_string="account_reward",
            limit=limit,
        )
        pagination = pagination_calculator(pagination_request)
        html = templates.get_template("block/block_payday_account_rewards.html").render(
            {
                "rewards": account_rewards,
                "user": user,
                "tags": tags,
                "net": "mainnet",
                "request": request,
                "pagination": pagination,
            }
        )
        return html


@router.get(
    "/ajax_payday_account_rewards_tabulator/{block_height}/{total_rows}",
    response_class=JSONResponse,
)
async def get_ajax_payday_account_rewards_tabulator(
    request: Request,
    block_height: int,
    total_rows: int,
    page: int = Query(),
    size: int = Query(),
    sort_key: Optional[str] = Query("account_id"),
    direction: Optional[str] = Query("asc"),
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    # limit = 30
    user: UserV2 = await get_user_detailsv2(request)
    if request.app.env["NET"] == "mainnet":
        # skip = calculate_skip(requested_page, total_rows, limit)
        skip = (page - 1) * size
        last_page = math.ceil(total_rows / size)

        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/mainnet/block/{block_height}/payday/account-rewards/{skip}/{size}/{sort_key}/{direction}",
            httpx_client,
        )
        account_rewards = api_result.return_value if api_result.ok else None
        for reward in account_rewards:
            reward["account_name"] = account_link(
                reward["account_id"], "mainnet", user, tags, request.app
            )
            reward["account_id"] = reward["account_id"][:4]

        return JSONResponse(
            {"data": account_rewards, "last_page": last_page, "last_row": total_rows}
        )
    else:
        return JSONResponse([])


@router.get(
    "/ajax_payday_pool_rewards_tabulator/{block_height}/{total_rows}",
    response_class=JSONResponse,
)
async def get_ajax_payday_pool_rewards_tabulator(
    request: Request,
    block_height: int,
    total_rows: int,
    page: int = Query(),
    size: int = Query(),
    sort_key: Optional[str] = Query("pool_owner"),
    direction: Optional[str] = Query("asc"),
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    # limit = 30
    user: UserV2 = await get_user_detailsv2(request)
    if request.app.env["NET"] == "mainnet":
        # skip = calculate_skip(requested_page, total_rows, limit)
        skip = (page - 1) * size
        last_page = math.ceil(total_rows / size)

        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/mainnet/block/{block_height}/payday/pool-rewards/{skip}/{size}/{sort_key}/{direction}",
            httpx_client,
        )
        pool_rewards = api_result.return_value if api_result.ok else None
        for reward in pool_rewards:
            if reward["pool_owner"] != "passive_delegation":
                reward["pool_name"] = account_link(
                    reward["pool_owner"], "mainnet", user, tags, request.app
                )

            else:
                reward["pool_name"] = "Passive Delegation"

        return JSONResponse(
            {"data": pool_rewards, "last_page": last_page, "last_row": total_rows}
        )
    else:
        return JSONResponse([])


# @router.get(
#     "/ajax_payday_pool_rewards_html_v2/{block_height}/{requested_page}/{total_rows}/{api_key}",
#     response_class=HTMLResponse,
# )
# async def get_ajax_payday_pool_rewards_html_v2(
#     request: Request,
#     block_height: int,
#     requested_page: int,
#     total_rows: int,
#     api_key: str,
#     tags: dict = Depends(get_labeled_accounts),
#     httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
# ):
#     limit = 30
#     user: UserV2 = await get_user_detailsv2(request)
#     if request.app.env["NET"] == "mainnet":
#         skip = calculate_skip(requested_page, total_rows, limit)
#         api_result = await get_url_from_api(
#             f"{request.app.api_url}/v2/mainnet/block/{block_height}/payday/pool-rewards/{skip}/{limit}",
#             httpx_client,
#         )
#         pool_rewards = api_result.return_value if api_result.ok else None
#         if not pool_rewards:
#             error = f"Request error getting pool rewards for block at {block_height} on mainnet."
#             return templates.TemplateResponse(
#                 "base/error-request.html",
#                 {
#                     "request": request,
#                     "error": error,
#                     "env": environment,
#                     "net": "mainnet",
#                 },
#             )

#         pagination_request = PaginationRequest(
#             total_txs=total_rows,
#             requested_page=requested_page,
#             word="pool-reward",
#             action_string="pool_reward",
#             limit=limit,
#         )
#         pagination = pagination_calculator(pagination_request)
#         html = templates.get_template("block/block_payday_pool_rewards.html").render(
#             {
#                 "rewards": pool_rewards,
#                 "user": user,
#                 "tags": tags,
#                 "net": "mainnet",
#                 "request": request,
#                 "pagination": pagination,
#             }
#         )
#         return html


@router.get(
    "/ajax_block_transactions_html_v2/{net}/{height}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def ajax_block_transactions_html(
    request: Request,
    net: str,
    height: int,
    requested_page: int,
    total_rows: int,
    api_key: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    limit = 20
    user: UserV2 = await get_user_detailsv2(request)

    skip = calculate_skip(requested_page, total_rows, limit)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/block/{height}/transactions/{skip}/{limit}",
        httpx_client,
    )
    tx_result = api_result.return_value if api_result.ok else None
    if not api_result.ok:
        error = f"Request error getting transactions for block at {height} on {net}."
        return templates.TemplateResponse(
            "base/error-request.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )

    made_up_txs = []
    if len(tx_result) > 0:
        for transaction in tx_result:
            transaction = CCD_BlockItemSummary(**transaction)
            makeup_request = MakeUpRequest(
                **{
                    "net": net,
                    "httpx_client": httpx_client,
                    "tags": tags,
                    "user": user,
                    "app": request.app,
                    "requesting_route": RequestingRoute.block,
                }
            )

            classified_tx = await MakeUp(
                makeup_request=makeup_request
            ).prepare_for_display(transaction, "", False)
            made_up_txs.append(classified_tx)

    pagination_request = PaginationRequest(
        total_txs=total_rows,
        requested_page=requested_page,
        word="tx",
        action_string="tx",
        limit=limit,
    )
    pagination = pagination_calculator(pagination_request)
    html = templates.get_template("block/block_transactions.html").render(
        {
            "transactions": made_up_txs,
            "tags": tags,
            "net": net,
            "request": request,
            "pagination": pagination,
            "totals_in_pagination": False,
        }
    )

    return html
