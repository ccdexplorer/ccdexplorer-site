from ccdexplorer_fundamentals.user_v2 import UserV2
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.env import environment
from app.jinja2_helpers import templates
from app.state import (
    get_httpx_client,
    get_labeled_accounts,
    get_user_detailsv2,
)
from app.classes.dressingroom import (
    MakeUp,
    MakeUpRequest,
    RequestingRoute,
)
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_BlockItemSummary,
    CCD_AccountPending,
)
import datetime as dt
from app.utils import (
    get_url_from_api,
    tx_type_translation,
)
import httpx
from pydantic import BaseModel

router = APIRouter()


@router.get(
    "/{net}/protocol-update-txs",
    response_class=HTMLResponse,
)
async def get_account_transactions(
    request: Request,
    net: str,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
    tags: dict = Depends(get_labeled_accounts),
):
    """ """
    user: UserV2 = await get_user_detailsv2(request)

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/misc/protocol-updates",
        httpx_client,
    )
    tx_result = api_result.return_value if api_result.ok else None
    if not tx_result:
        error = f"Request error getting protocol update transactions on {net}."
        return templates.TemplateResponse(
            "base/error-request.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )

    tx_result_transactions = tx_result  # ["transactions"]
    total_rows = 0

    made_up_txs = []
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
            made_up_txs.append(classified_tx)

    html = templates.get_template("base/transactions_simple_list.html").render(
        {
            "transactions": made_up_txs,
            "tags": tags,
            "user": user,
            "net": net,
            "show_amounts": True,
            "request": request,
            "totals_in_pagination": True,
            "total_rows": total_rows,
        }
    )

    return html


@router.get("/{net}/projects", response_class=HTMLResponse)
async def get_projects_overview(
    request: Request,
    net: str,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/mainnet/misc/projects/all-ids",
        httpx_client,
    )
    projects = api_result.return_value if api_result.ok else []

    return templates.TemplateResponse(
        "projects/projects.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "projects": projects,
            "net": "mainnet",
        },
    )


@router.get("/{net}/chain-information", response_class=HTMLResponse)
async def chain_information(
    request: Request,
    net: str,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/misc/identity-providers",
        httpx_client,
    )
    ip = api_result.return_value if api_result.ok else []

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/misc/anonymity-revokers",
        httpx_client,
    )
    ar = api_result.return_value if api_result.ok else []

    return templates.TemplateResponse(
        "tools/chain-information.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "ar": ar,
            "ip": ip,
            "net": "mainnet",
        },
    )


async def get_data_for_chain_transactions_for_dates(
    app, start_date: str, end_date: str
) -> list[str]:
    api_result = await get_url_from_api(
        f"{app.api_url}/v2/mainnet/misc/statistics-chain/{start_date}/{end_date}",
        app.httpx_client,
    )
    result = api_result.return_value if api_result.ok else []
    return result


@router.get(
    "/{net}/tools/labeled-accounts", response_class=HTMLResponse | RedirectResponse
)
async def labeled_accounts(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    # tags_community: dict = Depends(get_community_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/misc/projects/all-ids",
        httpx_client,
    )
    projects = api_result.return_value if api_result.ok else []
    if net == "mainnet":
        return templates.TemplateResponse(
            "/tools/labeled-accounts.html",
            {
                "env": environment,
                "request": request,
                "user": user,
                "tags": tags,
                "projects": projects,
                "net": net,
            },
        )
    else:
        response = RedirectResponse(
            url="/mainnet/tools/labeled-accounts", status_code=302
        )
        return response


class TodayInRequest(BaseModel):
    theme: str
    date: str


@router.post(
    "/{net}/ajax_today_in/",
    response_class=HTMLResponse,
)
async def ajax_today_in(
    request: Request,
    net: str,
    post_data: TodayInRequest,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/misc/today-in/{post_data.date}",
        httpx_client,
    )
    today_in = api_result.return_value if api_result.ok else []

    if net == "mainnet":
        return templates.TemplateResponse(
            "/tools/today_in_day.html",
            {
                "env": environment,
                "request": request,
                "user": user,
                "tags": tags,
                "today_in": today_in,
                "date": post_data.date,
                "net": net,
            },
        )


@router.get("/{net}/today-in", response_class=HTMLResponse | RedirectResponse)
async def today_in(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    # tags_community: dict = Depends(get_community_labeled_accounts),
):
    user: UserV2 = await get_user_detailsv2(request)
    yesterday = (dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    if net == "mainnet":
        return templates.TemplateResponse(
            "/tools/today_in.html",
            {
                "env": environment,
                "request": request,
                "user": user,
                "tags": tags,
                "yesterday": yesterday,
                "net": net,
            },
        )
    else:
        response = RedirectResponse(
            url="/mainnet/tools/labeled-accounts", status_code=302
        )
        return response


@router.get("/{net}/transactions-by-type", response_class=HTMLResponse)
async def transactions_by_type_page(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
) -> HTMLResponse:
    if net not in ["mainnet", "testnet"]:
        return RedirectResponse(url="/mainnet", status_code=302)

    user: UserV2 = await get_user_detailsv2(request)

    request.state.api_calls = {}
    request.state.api_calls["Latest Txs"] = (
        f"{request.app.api_url}/docs#/Transactions/get_last_transactions_v2__net__transactions_last__count__get"
    )

    return templates.TemplateResponse(
        "tools/transactions_by_type.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "net": net,
            "requested_page": 1,
            "API_KEY": request.app.env["CCDEXPLORER_API_KEY"],
        },
    )


class PostData(BaseModel):
    theme: str
    filter: str
    requested_page: int


@router.post("/{net}/ajax_last_transactions_by_type", response_class=HTMLResponse)
async def ajax_last_txs_by_type(
    request: Request,
    net: str,
    post_data: PostData,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    limit = 20
    skip = (post_data.requested_page - 1) * limit
    if net not in ["mainnet", "testnet"]:
        return RedirectResponse(url="/mainnet", status_code=302)

    user: UserV2 = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/transactions/last/{limit}/{skip}/{post_data.filter}",
        httpx_client,
    )
    latest_txs = api_result.return_value if api_result.ok else None
    if not latest_txs:
        error = f"Request error getting the most recent transactions on {net}."
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
    if len(latest_txs) > 0:
        for transaction in latest_txs:
            transaction = CCD_BlockItemSummary(**transaction)
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
            made_up_txs.append(classified_tx)

    html = templates.TemplateResponse(
        "tools/last_txs_table_by_type.html",
        {
            "request": request,
            "tx_type_translation": tx_type_translation,
            "transactions": made_up_txs,
            "net": net,
            "filter": post_data.filter,
            "pagination": None,
            "totals_in_pagination": False,
            "total_rows": 0,
            "requested_page": post_data.requested_page,
            "tags": tags,
            "user": user,
        },
    )

    return html


@router.get("/{net}/accounts-scheduled-release", response_class=HTMLResponse)
async def accounts_scheduled_release(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
) -> HTMLResponse:
    if net not in ["mainnet", "testnet"]:
        return RedirectResponse(url="/mainnet", status_code=302)

    user: UserV2 = await get_user_detailsv2(request)

    request.state.api_calls = {}
    request.state.api_calls["Accounts Scheduled Release"] = (
        f"{request.app.api_url}/docs#/Accounts/get_scheduled_release_accounts_v2__net__accounts_scheduled_release_get"
    )

    return templates.TemplateResponse(
        "tools/accounts-scheduled-release.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "net": net,
            "requested_page": 1,
            "API_KEY": request.app.env["CCDEXPLORER_API_KEY"],
        },
    )


@router.get(
    "/{net}/ajax_accounts_scheduled_release",
    response_class=HTMLResponse | RedirectResponse,
)
async def ajax_accounts_scheduled_release(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    # tags_community: dict = Depends(get_community_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/accounts/scheduled-release",
        httpx_client,
    )
    accounts = api_result.return_value if api_result.ok else []
    if accounts:
        accounts = [CCD_AccountPending(**x) for x in accounts]
    return templates.TemplateResponse(
        "/tools/accounts-scheduled-release-content.html",
        {
            "env": environment,
            "request": request,
            "user": user,
            "tags": tags,
            "accounts": accounts,
            "net": net,
        },
    )


@router.get("/{net}/accounts-cooldown", response_class=HTMLResponse)
async def accounts_cooldown(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
) -> HTMLResponse:
    if net not in ["mainnet", "testnet"]:
        return RedirectResponse(url="/mainnet", status_code=302)

    user: UserV2 = await get_user_detailsv2(request)

    request.state.api_calls = {}
    request.state.api_calls["Accounts Cooldown"] = (
        f"{request.app.api_url}/docs#/Accounts/get_cooldown_accounts_v2__net__accounts_cooldown_get"
    )
    request.state.api_calls["Accounts Pre Cooldown"] = (
        f"{request.app.api_url}/docs#/Accounts/get_pre_cooldown_accounts_v2__net__accounts_pre_cooldown_get"
    )
    request.state.api_calls["Accounts Pre Pre Cooldown"] = (
        f"{request.app.api_url}/docs#/Accounts/get_pre_pre_cooldown_accounts_v2__net__accounts_pre_pre_cooldown_get"
    )
    return templates.TemplateResponse(
        "tools/accounts-cooldown.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "net": net,
            "requested_page": 1,
            "API_KEY": request.app.env["CCDEXPLORER_API_KEY"],
        },
    )


@router.get(
    "/{net}/ajax_accounts_cooldown",
    response_class=HTMLResponse | RedirectResponse,
)
async def ajax_accounts_cooldown(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    # tags_community: dict = Depends(get_community_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/accounts/cooldown",
        httpx_client,
    )
    accounts = api_result.return_value if api_result.ok else []
    if accounts:
        accounts = [CCD_AccountPending(**x) for x in accounts]
    return templates.TemplateResponse(
        "/tools/accounts-cooldown-content.html",
        {
            "env": environment,
            "request": request,
            "user": user,
            "tags": tags,
            "accounts": accounts,
            "net": net,
        },
    )


@router.get(
    "/{net}/ajax_accounts_pre_cooldown",
    response_class=HTMLResponse | RedirectResponse,
)
async def ajax_accounts_pre_cooldown(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    # tags_community: dict = Depends(get_community_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/accounts/pre-cooldown",
        httpx_client,
    )
    accounts = api_result.return_value if api_result.ok else []
    # if accounts:
    #     accounts = [CCD_AccountPending(**x) for x in accounts]
    return templates.TemplateResponse(
        "/tools/accounts-pre-cooldown-content.html",
        {
            "env": environment,
            "request": request,
            "user": user,
            "tags": tags,
            "accounts": accounts,
            "net": net,
        },
    )


@router.get(
    "/{net}/ajax_accounts_pre_pre_cooldown",
    response_class=HTMLResponse | RedirectResponse,
)
async def ajax_accounts_pre_pre_cooldown(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    # tags_community: dict = Depends(get_community_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/accounts/pre-pre-cooldown",
        httpx_client,
    )
    accounts = api_result.return_value if api_result.ok else []
    # if accounts:
    #     accounts = [CCD_AccountPending(**x) for x in accounts]
    return templates.TemplateResponse(
        "/tools/accounts-pre-pre-cooldown-content.html",
        {
            "env": environment,
            "request": request,
            "user": user,
            "tags": tags,
            "accounts": accounts,
            "net": net,
        },
    )
