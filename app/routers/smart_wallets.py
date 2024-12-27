from ccdexplorer_fundamentals.user_v2 import UserV2
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import CCD_BlockItemSummary
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
)
import httpx
from pydantic import BaseModel

router = APIRouter()


class SearchRequestPublicKey(BaseModel):
    selector: str
    value: str
    net: str


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
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/smart-wallet/{index}/{subindex}/public-key/{public_key}/logged-events/0/10",
        httpx_client,
    )
    logged_events = api_result.return_value if api_result.ok else None

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/smart-wallet/{index}/{subindex}/public-key/{public_key}/balances",
        httpx_client,
    )
    balances = api_result.return_value if api_result.ok else None
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
            "logged_events": logged_events,
        },
    )


@router.get("/{net}/smart-wallets", response_class=HTMLResponse)
async def get_smart_wallets_overview(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    request.state.api_calls = {}

    user: UserV2 = await get_user_detailsv2(request)
    # # api_result = await get_url_from_api(
    # #     f"{request.app.api_url}/v2/{net}/transaction/{tx_hash}", httpx_client
    # # )
    # # result = CCD_BlockItemSummary(**api_result.return_value) if api_result.ok else None
    # # if not result:
    # #     error = f"Can't find the transaction at {tx_hash} on {net}."
    # #     return templates.TemplateResponse(
    # #         "base/error.html",
    # #         {
    # #             "request": request,
    # #             "error": error,
    # #             "env": environment,
    # #             "net": net,
    # #         },
    # #     )

    # makeup_request = MakeUpRequest(
    #     **{
    #         "net": net,
    #         "httpx_client": httpx_client,
    #         "tags": tags,
    #         "user": user,
    #         "ccd_historical": None,
    #         "app": request.app,
    #         "requesting_route": RequestingRoute.transaction,
    #     }
    # )
    # classified_tx = await MakeUp(makeup_request=makeup_request).prepare_for_display(
    #     result, "", False
    # )
    # tx_with_makeup = classified_tx.dct
    # request.state.api_calls["Transaction Info"] = (
    #     f"{request.app.api_url}/docs#/Transaction/get_transaction_v2__net__transaction__tx_hash__get"
    # )
    return templates.TemplateResponse(
        "smart_wallets/sw_overview.html",
        {
            "request": request,
            "net": net,
            "tags": tags,
            "user": user,
            "env": environment,
        },
    )
