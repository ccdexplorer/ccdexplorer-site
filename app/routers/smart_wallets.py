from ccdexplorer_fundamentals.user_v2 import UserV2
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_BlockItemSummary,
    CCD_ContractAddress,
)
from app.jinja2_helpers import templates
from app.env import environment
from app.classes.dressingroom import MakeUp, MakeUpRequest, RequestingRoute
from app.state import get_labeled_accounts, get_user_detailsv2, get_httpx_client
from app.utils import (
    PaginationRequest,
    account_link,
    calculate_skip,
    pagination_calculator,
    ccdexplorer_plotly_template,
    add_account_info_to_cache,
    from_address_to_index,
    get_url_from_api,
    tx_type_translation,
)
import httpx
from pydantic import BaseModel
from enum import Enum

router = APIRouter()


class SearchRequestPublicKey(BaseModel):
    selector: str
    value: str
    net: str


cis5_event_translations = {
    "CIS-5.nonce_event": "Nonce",
    "CIS-5.deposit_ccd_event": "Deposit",
    "CIS-5.deposit_cis2_tokens_event": "Deposit",
    "CIS-5.withdraw_ccd_event": "Withdraw",
    "CIS-5.withdraw_cis2_tokens_event": "Withdraw",
    "CIS-5.transfer_ccd_event": "Transfer",
    "CIS-5.transfer_cis2_tokens_event": "Transfer",
}


@router.post(
    "/{net}/smart-wallets/search",
    response_class=RedirectResponse,
)
async def search_public_key(request: Request, search_request: SearchRequestPublicKey):
    url = f"/{search_request.net}/smart-wallet/{int(search_request.selector)}/0/{search_request.value}"
    if url:
        response = RedirectResponse(url=url, status_code=200)
        # note do not remove this header! Very strange things will happen.
        # The new route is requested, however the browser page remains the same!
        response.headers["HX-Redirect"] = url
        return response


@router.get(
    "/smart_wallet_events/{net}/{index}/{subindex}/{public_key}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def get_public_key_events(
    request: Request,
    net: str,
    index: int,
    subindex: int,
    public_key: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
    # recurring: Recurring = Depends(get_recurring),
    tags: dict = Depends(get_labeled_accounts),
):
    """ """
    limit = 10
    user: UserV2 = await get_user_detailsv2(request)

    skip = calculate_skip(requested_page, total_rows, limit)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/smart-wallet/{index}/{subindex}/public-key/{public_key}/balances",
        httpx_client,
    )
    balances = api_result.return_value if api_result.ok else None

    balances_all = (
        balances["ccd"]
        | balances["fungible"]
        | balances["non_fungible"]
        | balances["unverified"]
    )
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/smart-wallet/{index}/{subindex}/public-key/{public_key}/logged-events/{skip}/{limit}",
        httpx_client,
    )
    logged_events = api_result.return_value if api_result.ok else None
    if not logged_events:
        error = (
            f"Request error getting logged events for account at {public_key} on {net}."
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

    total_rows = logged_events["all_logged_events_count"]
    pagination_request = PaginationRequest(
        total_txs=total_rows,
        requested_page=requested_page,
        word="event",
        action_string="cis5_event",
        limit=limit,
    )
    pagination = pagination_calculator(pagination_request)
    html = templates.get_template("smart_wallets/public_key_events.html").render(
        {
            "logged_events": logged_events,
            "tags": tags,
            "net": net,
            "request": request,
            "pagination": pagination,
            "totals_in_pagination": True,
            "total_rows": total_rows,
            "cis5_event_translations": cis5_event_translations,
            "balances_all": balances_all,
            "balances": balances,
        }
    )

    return html


@router.get(
    "/{net}/smart-wallet/{index}/{subindex}/{public_key}", response_class=HTMLResponse
)
async def get_public_key_page(
    request: Request,
    net: str,
    index: int,
    subindex: int,
    public_key: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    request.state.api_calls = {}
    user: UserV2 = await get_user_detailsv2(request)
    wallet_contract_address = CCD_ContractAddress.from_index(index, subindex).to_str()

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/smart-wallet/{index}/{subindex}/public-key/{public_key}/balances",
        httpx_client,
    )
    balances = api_result.return_value if api_result.ok else None

    balance_ccd = balances["ccd"]
    balances_fungible = balances["fungible"]
    balances_non_fungible = balances["non_fungible"]
    balances_unverified = balances["unverified"]
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/smart-wallet/{index}/{subindex}/public-key/{public_key}/deployed",
        httpx_client,
    )
    tx_deployed = (
        CCD_BlockItemSummary(**api_result.return_value) if api_result.ok else None
    )

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/smart-wallet/{index}/{subindex}/public-key/{public_key}/transaction-count",
        httpx_client,
    )
    tx_count_dict = api_result.return_value if api_result.ok else 0

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/smart-wallets/overview",
        httpx_client,
    )
    smart_wallets = api_result.return_value if api_result.ok else None
    cis2_tokens_available = (
        (len(balances_fungible) > 0)
        or (len(balances_non_fungible) > 0)
        or (len(balances_unverified) > 0)
    )
    return templates.TemplateResponse(
        "smart_wallets/sw_public_key_page.html",
        {
            "request": request,
            "net": net,
            "tags": tags,
            "user": user,
            "env": environment,
            "index": index,
            "subindex": subindex,
            "public_key": public_key,
            "balances": balances,
            "balance_ccd": balance_ccd,
            "balances_fungible": balances_fungible,
            "balances_non_fungible": balances_non_fungible,
            "balances_unverified": balances_unverified,
            # "logged_events": logged_events,
            "tx_deployed": tx_deployed,
            "tx_count_dict": tx_count_dict,
            "smart_wallets": smart_wallets,
            "wallet_contract_address": wallet_contract_address,
            "cis2_tokens_available": cis2_tokens_available,
        },
    )


# @router.get("/{net}/smart-wallets", response_class=HTMLResponse)
# async def get_smart_wallets_overview(
#     request: Request,
#     net: str,
#     tags: dict = Depends(get_labeled_accounts),
#     httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
# ):
#     request.state.api_calls = {}

#     user: UserV2 = await get_user_detailsv2(request)
#     api_result = await get_url_from_api(
#         f"{request.app.api_url}/v2/{net}/smart-wallets/overview/all",
#         httpx_client,
#     )
#     smart_wallets = api_result.return_value if api_result.ok else None
#     return templates.TemplateResponse(
#         "smart_wallets/sw_overview.html",
#         {
#             "request": request,
#             "net": net,
#             "tags": tags,
#             "user": user,
#             "env": environment,
#             "smart_wallets": smart_wallets,
#         },
#     )


@router.get("/{net}/smart-wallets", response_class=HTMLResponse)
async def get_smart_wallets_overview_with_txs(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    request.state.api_calls = {}

    user: UserV2 = await get_user_detailsv2(request)
    # api_result = await get_url_from_api(
    #     f"{request.app.api_url}/v2/{net}/smart-wallets/overview/all",
    #     httpx_client,
    # )
    # smart_wallets = api_result.return_value if api_result.ok else None
    return templates.TemplateResponse(
        "smart_wallets/sw_overview_with_txs.html",
        {
            "request": request,
            "net": net,
            "tags": tags,
            "user": user,
            "env": environment,
            # "smart_wallets": smart_wallets,
        },
    )


@router.get(
    "/{net}/ajax_smart_wallets_txs/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def ajax_last_txs_for_smart_wallets(
    request: Request,
    net: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    limit = 20
    requested_page = max(0, requested_page)
    skip = calculate_skip(requested_page, total_rows, limit)
    if net not in ["mainnet", "testnet"]:
        return RedirectResponse(url="/mainnet", status_code=302)

    user: UserV2 = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/smart-wallets/transactions/{skip}/{limit}",
        httpx_client,
    )
    smart_wallet_txs = api_result.return_value if api_result.ok else None
    if not smart_wallet_txs:
        error = f"Request error getting the most recent transactions for smart wallets on {net}."
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
    if len(smart_wallet_txs) > 0:
        for transaction_plus in smart_wallet_txs.values():
            transaction = CCD_BlockItemSummary(**transaction_plus["tx"])
            makeup_request = MakeUpRequest(
                **{
                    "net": net,
                    "httpx_client": httpx_client,
                    "tags": tags,
                    "user": user,
                    "app": request.app,
                    "requesting_route": RequestingRoute.other,
                }
            )

            classified_tx = await MakeUp(
                makeup_request=makeup_request
            ).prepare_for_display(transaction, "", False)
            classified_tx.wallet_contract_address = transaction_plus[
                "wallet_contract_address"
            ]
            classified_tx.public_key = transaction_plus["public_key"]
            made_up_txs.append(classified_tx)

    pagination_request = PaginationRequest(
        total_txs=limit,
        no_totals=True,
        returned_rows=len(made_up_txs),
        requested_page=requested_page,
        word="tx",
        action_string="tx",
        limit=limit,
    )
    pagination = pagination_calculator(pagination_request)
    html = templates.TemplateResponse(
        "smart_wallets/transactions_sw.html",
        {
            "request": request,
            "tx_type_translation": tx_type_translation,
            "transactions": made_up_txs,
            "pagination": pagination,
            "totals_in_pagination": False,
            "total_rows": 10,
            "show_wallet_contract_address": True,
            "net": net,
            "tags": tags,
            "user": user,
        },
    )

    return html
