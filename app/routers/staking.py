# ruff: noqa: F403, F405, E402, E501, E722
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse


from app.env import environment
from app.jinja2_helpers import templates
from app.classes.Enums import PoolStatus

from ccdexplorer_fundamentals.mongodb import (
    Collections,
    MongoTypePayday,
    MongoTypePaydaysPerformance,
)

from app.utils import (
    calculate_skip,
    get_url_from_api,
    pagination_calculator,
    PaginationRequest,
)
from app.state import (
    get_httpx_client,
    get_labeled_accounts,
    get_user_detailsv2,
)

from ccdexplorer_fundamentals.user_v2 import UserV2
import httpx

router = APIRouter()


@router.get("/{net}/staking")  # type:ignore
async def staking(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 = await get_user_detailsv2(request)
    request.state.api_calls = {}
    request.state.api_calls["Paydays"] = (
        f"{request.app.api_url}/docs#/Accounts/get_paydays_v2__net__accounts_paydays__skip___limit__get"
    )
    request.state.api_calls["Pools"] = (
        f"{request.app.api_url}/docs#/Accounts/get_payday_pools_v2__net__accounts_paydays_pools__status__get"
    )
    request.state.api_calls["Passive Delegation Info"] = (
        f"{request.app.api_url}/docs#/Accounts/get_payday_passive_info_v2__net__accounts_paydays_passive_delegation_get"
    )
    request.state.api_calls["Passive Delegators"] = (
        f"{request.app.api_url}/docs#/Accounts/get_payday_passive_delegators_v2__net__accounts_paydays_passive_delegators__skip___limit__get"
    )
    if net == "mainnet":
        return templates.TemplateResponse(
            "staking/staking.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                # "passive_object": passive_object,
                # "passive_info_v2": passive_info_v2,
                "user": user,
            },
        )
    else:
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "user": user,
            },
        )


@router.get(
    "/{net}/ajax_paydays_passive/",
    response_class=HTMLResponse,
)
async def get_ajax_payday_passive(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 = await get_user_detailsv2(request)
    if net != "mainnet":
        return None
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/mainnet/accounts/paydays/passive-delegation",
        httpx_client,
    )
    passive_info = api_result.return_value if api_result.ok else {}

    if not passive_info:
        error = "Request error getting passive info on mainnet."
        return templates.TemplateResponse(
            "base/error-request.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": "mainnet",
            },
        )

    html = templates.get_template("staking/staking_passive_info_rewards.html").render(
        {
            "passive_info": passive_info,
            "user": user,
            "tags": tags,
            "net": "mainnet",
            "request": request,
        }
    )
    return html


#### tabulator ####
@router.get("/{net}/ajax_paydays")
async def get_ajax_paydays(
    request: Request,
    net: str,
    page: int = 1,  # from Tabulator
    size: int = 15,  # page size
    api_key: str = "",
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 = await get_user_detailsv2(request)
    skip = (page - 1) * size

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/accounts/paydays/{skip}/{size}",
        httpx_client,
    )
    paydays = (
        [MongoTypePayday(**x) for x in api_result.return_value] if api_result.ok else []
    )
    return {
        "data": paydays,  # must be a list
        # "last_page": math.ceil(api_result["total"] / size),
        # "total_count": api_result["total"],  # optional
    }


@router.get(
    "/{net}/ajax_paydays/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_paydays_tabulator(
    request: Request,
    net: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    limit = 15
    user: UserV2 = await get_user_detailsv2(request)
    if net == "mainnet":
        skip = calculate_skip(requested_page, total_rows, limit)
        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/mainnet/accounts/paydays/{skip}/{limit}",
            httpx_client,
        )
        paydays = (
            [MongoTypePayday(**x) for x in api_result.return_value]
            if api_result.ok
            else []
        )
        if not paydays:
            error = "Request error getting paydays on mainnet."
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
            word="payday",
            action_string="payday",
            limit=limit,
            returned_rows=len(paydays),
        )
        pagination = pagination_calculator(pagination_request)
        html = templates.get_template("staking/staking_paydays_v2.html").render(
            {
                "paydays": paydays,
                "user": user,
                "tags": tags,
                "net": "mainnet",
                "request": request,
                "pagination": pagination,
            }
        )
        return html


#### tabulator ####


@router.get(
    "/{net}/ajax_paydays/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_paydays(
    request: Request,
    net: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    limit = 15
    user: UserV2 = await get_user_detailsv2(request)
    if net == "mainnet":
        skip = calculate_skip(requested_page, total_rows, limit)
        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/mainnet/accounts/paydays/{skip}/{limit}",
            httpx_client,
        )
        paydays = (
            [MongoTypePayday(**x) for x in api_result.return_value]
            if api_result.ok
            else []
        )
        if not paydays:
            error = "Request error getting paydays on mainnet."
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
            word="payday",
            action_string="payday",
            limit=limit,
            returned_rows=len(paydays),
        )
        pagination = pagination_calculator(pagination_request)
        html = templates.get_template("staking/staking_paydays_v2.html").render(
            {
                "paydays": paydays,
                "user": user,
                "tags": tags,
                "net": "mainnet",
                "request": request,
                "pagination": pagination,
            }
        )
        return html


@router.get(
    "/ajax_pools/{status}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_pools(
    request: Request,
    status: str,
    api_key: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):

    user: UserV2 = await get_user_detailsv2(request)

    enhanced_pools = request.app.staking_pools_cache.get(status, {})

    html = templates.get_template("staking/staking_pools_v2.html").render(
        {
            "pools": enhanced_pools,
            "user": user,
            "tags": tags,
            "net": "mainnet",
            "request": request,
            "status": status,
            "PoolStatus": PoolStatus,
        }
    )
    return html


@router.get(
    "/ajax_passive_delegators/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_passive_delegators(
    request: Request,
    requested_page: int,
    total_rows: int,
    api_key: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    limit = 10
    user: UserV2 = await get_user_detailsv2(request)
    skip = calculate_skip(requested_page, total_rows, limit)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/mainnet/accounts/paydays/passive-delegators/{skip}/{limit}",
        httpx_client,
    )
    passive_delegators_response = api_result.return_value if api_result.ok else []
    delegators = passive_delegators_response["delegators"]

    pagination_request = PaginationRequest(
        total_txs=total_rows,
        requested_page=requested_page,
        word="delegator",
        action_string="delegator",
        limit=limit,
        returned_rows=len(delegators),
    )
    pagination = pagination_calculator(pagination_request)
    html = templates.get_template("staking/staking_passive_delegators.html").render(
        {
            "delegators": delegators,
            "user": user,
            "tags": tags,
            "net": "mainnet",
            "request": request,
            "pagination": pagination,
            "passive_delegators_response": passive_delegators_response,
        }
    )
    return html
