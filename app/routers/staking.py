# ruff: noqa: F403, F405, E402, E501, E722
import math

import httpx
from ccdexplorer_fundamentals.mongodb import (
    MongoTypePayday,
)
import dateutil
from dateutil import parser
from ccdexplorer_fundamentals.user_v2 import UserV2
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.classes.Enums import PoolStatus
from app.env import environment
from app.jinja2_helpers import templates
from app.state import (
    get_httpx_client,
    get_labeled_accounts,
    get_user_detailsv2,
)
from app.utils import (
    PaginationRequest,
    calculate_skip,
    get_url_from_api,
    pagination_calculator,
    round_x_decimal_with_comma,
    create_dict_for_tabulator_display_for_pools,
    account_link,
    humanize_age,
)

router = APIRouter()


@router.get("/{net}/staking")  # type:ignore
async def staking(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 | None = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/passive_delegation/staking-rewards-object/passive_delegation",
        httpx_client,
    )
    account_apy_object = api_result.return_value if api_result.ok else None

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
        all_pools: dict = request.app.staking_pools_cache
        made_up_pools = []
        for pool in all_pools:
            if "baker_id" in pool:
                made_up_pools.append(
                    create_dict_for_tabulator_display_for_pools("mainnet", pool)
                )
        suspended_data = []
        for suspended_id, value in request.app.primed_suspended_cache.get(
            "suspended_validators"
        ).items():
            suspended_data.append(
                {
                    "validator_id": f'<a class="" href="/{net}/account/{suspended_id}"><i class="bi bi-person-bounding-box pe-1"></i><span style="font-family: monospace, monospace;" class="small">{suspended_id}</span></a>',
                    "suspended_since": f'<span class="ccd">{dateutil.parser.parse(value[0]):%Y-%m-%d}</span>',
                    "suspended_days": f'<span class="ccd">{humanize_age(dateutil.parser.parse(value[0]))}</span>',
                    "count_of_suspension": f'<span class="ccd">{len(value)}</span>',
                    "count_of_primed": f'<span class="ccd">{len(
                        request.app.primed_suspended_cache.get("primed_validators").get(
                            suspended_id, []
                        )
                    )}</span>',
                    "validator_id_download": suspended_id,
                    "suspended_since_download": f"{dateutil.parser.parse(value[0]):%Y-%m-%d}",
                    "suspended_days_download": humanize_age(
                        dateutil.parser.parse(value[0])
                    ),
                    "count_of_suspension_download": len(value),
                    "count_of_primed_download": len(
                        request.app.primed_suspended_cache.get("primed_validators").get(
                            suspended_id, []
                        )
                    ),
                }
            )

        return templates.TemplateResponse(
            "staking/staking_tabs.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "delegation": True,
                "passive_delegation": True,
                "account_apy_object": account_apy_object,
                "suspended_data": suspended_data,
                "all_pools": made_up_pools,
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
    user: UserV2 | None = await get_user_detailsv2(request)
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
# @router.get("/{net}/ajax_paydays")
# async def get_ajax_paydays(
#     request: Request,
#     net: str,
#     page: int = 1,  # from Tabulator
#     size: int = 15,  # page size
#     api_key: str = "",
#     tags: dict = Depends(get_labeled_accounts),
#     httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
# ):
#     user: UserV2 | None = await get_user_detailsv2(request)
#     skip = (page - 1) * size

#     api_result = await get_url_from_api(
#         f"{request.app.api_url}/v2/{net}/accounts/paydays/{skip}/{size}",
#         httpx_client,
#     )
#     paydays = (
#         [MongoTypePayday(**x) for x in api_result.return_value] if api_result.ok else []
#     )
#     return {
#         "data": paydays,  # must be a list
#         # "last_page": math.ceil(api_result["total"] / size),
#         # "total_count": api_result["total"],  # optional
#     }


@router.get(
    "/{net}/ajax_paydays",
    response_class=HTMLResponse,
)
async def get_ajax_paydays_tabulator(
    request: Request,
    net: str,
    page: int = Query(),
    size: int = Query(),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):

    if net == "mainnet":
        skip = (page - 1) * size

        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/mainnet/accounts/paydays/{skip}/{size}",
            httpx_client,
        )
        return_dict = api_result.return_value if api_result.ok else {}

        if return_dict == {}:
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

        paydays = return_dict["result"]  # type: ignore
        made_up_paydays = []
        for p in paydays:
            made_up_payday = {}
            made_up_payday["block_height"] = (
                f'<a href="/{net}/block/{p['height_for_last_block']+1}"><span class="ccd">{round_x_decimal_with_comma(p['height_for_last_block']+1, 0)}</span></a>'
            )
            made_up_payday["payday_block_slot_time"] = parser.parse(
                p["payday_block_slot_time"]
            ).isoformat()
            made_up_payday["count_of_blocks"] = (
                p["height_for_last_block"] - p["height_for_first_block"] + 1
            )
            # download
            made_up_payday["block_height_download"] = p["height_for_last_block"] + 1
            made_up_payday["payday_block_slot_time_download"] = (
                f"{parser.parse(p["payday_block_slot_time"]):%Y-%m-%dT%H:%M:%S.%fZ}"
            )
            made_up_paydays.append(made_up_payday)

        total_rows = return_dict["total_rows"]  # type: ignore
        last_page = math.ceil(total_rows / size)
        return JSONResponse(
            {
                "data": made_up_paydays,
                "last_page": max(1, last_page),
                "last_row": total_rows,
            }
        )


@router.get("/mainnet/ajax_pools", response_class=HTMLResponse)
async def get_ajax_pools(
    request: Request,
    page: int = Query(),
    size: int = Query(),
    sort_key: str = Query(),
    direction: str = Query(),
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):

    all_pools: dict = request.app.staking_pools_cache

    made_up_pools = []
    for pool in all_pools:
        if "baker_id" in pool:
            made_up_pools.append(
                create_dict_for_tabulator_display_for_pools("mainnet", pool)
            )
    total_rows = len(made_up_pools)  # type: ignore
    last_page = math.ceil(total_rows / size)
    return JSONResponse(
        {
            "data": made_up_pools,
            "last_page": max(1, last_page),
            "last_row": total_rows,
        }
    )


@router.get(
    "/ajax_passive_delegators/{t}",
    response_class=HTMLResponse,
)
async def get_ajax_passive_delegators(
    request: Request,
    t: int,
    page: int = Query(),
    size: int = Query(),
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 | None = await get_user_detailsv2(request)
    skip = (page - 1) * size
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/mainnet/accounts/paydays/passive-delegators/{skip}/{size}",
        httpx_client,
    )
    passive_delegators_response = api_result.return_value if api_result.ok else {}
    delegators = passive_delegators_response["delegators"]  # type: ignore
    made_up_delegators = []
    for d in delegators:
        made_up_delegator = {}
        made_up_delegator["account"] = account_link(
            d["account"],
            "mainnet",
            user=user,
            tags=tags,
            app=request.app,
        )

        made_up_delegator["staked_amount"] = d["stake"]
        # download
        made_up_delegator["account_download"] = d["account"]
        made_up_delegators.append(made_up_delegator)

    total_rows = passive_delegators_response["total_rows"]  # type: ignore
    last_page = math.ceil(total_rows / size)
    return JSONResponse(
        {
            "data": made_up_delegators,
            "last_page": max(1, last_page),
            "last_row": total_rows,
        }
    )
