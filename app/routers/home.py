import datetime as dt
import os
from enum import Enum

import httpx
import pandas as pd
import plotly.express as px
from ccdexplorer_fundamentals.credential import Identity
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_AccountInfo,
    CCD_BlockInfo,
    CCD_BlockItemSummary,
    CCD_ConsensusDetailedStatus,
)
from ccdexplorer_fundamentals.mongodb import (
    MongoTypeInstance,
)
from ccdexplorer_fundamentals.user_v2 import UserV2
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel

from app.env import environment
from app.jinja2_helpers import templates
from app.state import get_httpx_client, get_labeled_accounts, get_user_detailsv2
from app.utils import (
    ccdexplorer_plotly_template,
    get_url_from_api,
    millify,
    tx_type_translation,
)

router = APIRouter()


class MarketCapInfo(Enum):
    TPS = 0
    TX_COUNT = 1
    TOKENS_COUNT = 2
    CMC = 3
    ACCOUNTS_COUNT = 4
    VALIDATORS_COUNT = 5


async def get_marketcap_info(
    httpx_client: httpx.AsyncClient,
    info: MarketCapInfo,
    api_url: str,
    net: str = "mainnet",
):
    if info == MarketCapInfo.TPS:
        url = f"{api_url}/v2/{net}/transactions/info/tps"
    elif info == MarketCapInfo.TX_COUNT:
        url = f"{api_url}/v2/{net}/transactions/info/count"
    elif info == MarketCapInfo.TOKENS_COUNT:
        url = f"{api_url}/v2/{net}/tokens/info/count"
    elif info == MarketCapInfo.CMC:
        url = f"{api_url}/v2/markets/info"
    elif info == MarketCapInfo.ACCOUNTS_COUNT:
        url = f"{api_url}/v2/{net}/accounts/info/count"
    elif info == MarketCapInfo.VALIDATORS_COUNT:
        url = f"{api_url}/v2/{net}/misc/validator-nodes/count"

    api_result = await get_url_from_api(url, httpx_client)
    response = api_result.return_value if api_result.ok else None
    return response


@router.get("/", response_class=RedirectResponse)
async def home(
    request: Request,
) -> RedirectResponse:
    response = RedirectResponse(url="/mainnet", status_code=302)
    return response


@router.get("/{net}", response_class=HTMLResponse)
async def redirect_to_mainnet(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
) -> HTMLResponse:
    if net not in ["mainnet", "testnet"]:
        return RedirectResponse(url="/mainnet", status_code=302)
    user: UserV2 = await get_user_detailsv2(request)
    request.state.api_calls = {}
    if "last_requests" not in request.state._state:
        request.state.last_requests = {}

    if net == "mainnet":
        request.state.api_calls["TPS"] = (
            f"{request.app.api_url}/docs#/Transactions/get_transactions_tps_v2__net__transactions_info_tps_get"
        )
        request.state.api_calls["Markets Info"] = (
            f"{request.app.api_url}/docs#/Markets/get_markets_info_v2_markets_info_get"
        )

    request.state.api_calls["Tx Count"] = (
        f"{request.app.api_url}/docs#/Transactions/get_transactions_count_estimate_v2__net__transactions_info_count_get"
    )

    request.state.api_calls["Account Count"] = (
        f"{request.app.api_url}/docs#/Accounts/get_accounts_count_estimate_v2__net__accounts_info_count_get"
    )
    request.state.api_calls["Latest Blocks"] = (
        f"{request.app.api_url}/docs#/Blocks/get_last_blocks_v2__net__blocks_last__count__get"
    )
    request.state.api_calls["Latest Txs"] = (
        f"{request.app.api_url}/docs#/Transactions/get_last_transactions_v2__net__transactions_last__count__get"
    )
    return templates.TemplateResponse(
        "home/home.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "net": net,
            "API_KEY": request.app.env["CCDEXPLORER_API_KEY"],
        },
    )


@router.post("/mainnet/ajax_market_cap_table", response_class=HTMLResponse)
async def ajax_market_cap_table(
    request: Request,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    theme = "dark"
    body = await request.body()
    if body:
        theme = body.decode("utf-8").split("=")[1]

    api_url = request.app.api_url

    tps_table = {"hour_tps": 0}
    total_txs = 0
    total_accounts = 0
    total_tokens = 0
    total_validators = 0

    try:

        tps_table = await get_marketcap_info(httpx_client, MarketCapInfo.TPS, api_url)
        if not tps_table:
            tps_table = {"hour_tps": 0}

        total_txs = await get_marketcap_info(
            httpx_client, MarketCapInfo.TX_COUNT, api_url, "mainnet"
        )
        if not total_txs:
            total_txs = 0

        total_tokens = await get_marketcap_info(
            httpx_client, MarketCapInfo.TOKENS_COUNT, api_url, "mainnet"
        )
        if not total_tokens:
            total_tokens = 0

        cmc = await get_marketcap_info(httpx_client, MarketCapInfo.CMC, api_url)
        if not cmc:
            cmc = {
                "cmc_rank": 0,
                "quote": {
                    "USD": {
                        "price": 0,
                        "percent_change_24h": 0,
                        "market_cap": 0,
                    }
                },
            }
        total_accounts = await get_marketcap_info(
            httpx_client, MarketCapInfo.ACCOUNTS_COUNT, api_url
        )
        if not total_accounts:
            total_accounts = 0

        total_validators = await get_marketcap_info(
            httpx_client, MarketCapInfo.VALIDATORS_COUNT, api_url
        )
        if not total_validators:
            total_validators = 0

    except Exception as error:
        print(error)

    if "last_requests" not in request.state._state:
        request.state.last_requests = {}
    html = templates.TemplateResponse(
        "home/crypto_dashboard.html",
        {
            "request": request,
            "net": "mainnet",
            "theme": theme,
            "cmc_rank": cmc["cmc_rank"],
            "tps_h": tps_table["hour_tps"],
            "total_txs": millify(total_txs),
            "total_validators": total_validators,
            "ccd_price": f"{cmc['quote']['USD']['price']:,.5f}",
            "ccd_change": cmc["quote"]["USD"]["percent_change_24h"],
            "market_cap": millify(float(cmc["quote"]["USD"]["market_cap"])),
            "total_accounts": f"{total_accounts:,.0f}",
            "total_tokens": f"{(total_tokens/1_000_000):,.1f} M",
        },
    )
    request.state.last_requests["marketcap"] = html
    return html


@router.get("/{net}/search_all/{value}", response_class=HTMLResponse)
async def search_all(
    request: Request,
    net: str,
    value: int | str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
) -> HTMLResponse:
    if net not in ["mainnet", "testnet"]:
        return RedirectResponse(url="/mainnet", status_code=302)

    user: UserV2 = await get_user_detailsv2(request)

    # order: account, block, transaction, module, instance, token
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/accounts/search/{value}",
        httpx_client,
    )
    accounts_list = api_result.return_value if api_result.ok else []

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/block/{value}",
        httpx_client,
    )
    block_info = CCD_BlockInfo(**api_result.return_value) if api_result.ok else None

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/transaction/{value}", httpx_client
    )
    tx = CCD_BlockItemSummary(**api_result.return_value) if api_result.ok else None

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/contract/{value}/0/info",
        httpx_client,
    )
    contract = MongoTypeInstance(**api_result.return_value) if api_result.ok else None

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/module/{value}",
        httpx_client,
    )
    module = api_result.return_value if api_result.ok else None

    html = templates.TemplateResponse(
        "home/search_all.html",
        {
            "request": request,
            "env": environment,
            "net": net,
            "tags": tags,
            "user": user,
            "accounts_list": accounts_list,
            "block_info": block_info,
            "tx": tx,
            "contract": contract,
            "module": module,
            "search_value": value,
        },
    )

    return html


class SearchRequest(BaseModel):
    selector: str
    value: str
    net: str


@router.post(
    "/search",
    response_class=RedirectResponse,
)
async def search(request: Request, search_request: SearchRequest):
    if search_request.selector == "all":
        url = f"/{search_request.net}/search_all/{search_request.value}"
    if search_request.selector == "account":
        url = f"/{search_request.net}/account/{search_request.value.replace(" ","")}"
    if search_request.selector == "block":

        url = f"/{search_request.net}/block/{search_request.value.replace(" ","").replace(",","").replace(".","")}"
    if search_request.selector == "transaction":
        url = (
            f"/{search_request.net}/transaction/{search_request.value.replace(" ","")}"
        )
    if search_request.selector == "contract":
        url = f"/{search_request.net}/contract/{search_request.value.replace(" ","")}/0"
    if search_request.selector == "module":
        url = f"/{search_request.net}/module/{search_request.value.replace(" ","")}"
    if search_request.selector == "token":
        search_request.value = search_request.value.replace(" ", "")
        if "-" in search_request.value:
            splits = search_request.value.split("-")
            if len(splits) == 2:
                contract_index = splits[0]
                try:
                    contract_index = int(contract_index)
                except:  # noqa: E722
                    pass
                if isinstance(contract_index, str):
                    tag = contract_index
                    contract_index = None
                    token_id = splits[1]
                    url = f"/{search_request.net}/tokens/{tag}/{token_id}"
                else:
                    token_id = splits[1]
                    url = f"/{search_request.net}/token/{contract_index}/0/{token_id}"
            else:
                # it's a tag name with a - in it...
                token_id = splits[len(splits) - 1]
                tag = "-".join(splits[: (len(splits) - 1)])
                url = f"/{search_request.net}/tokens/{tag}/{token_id}"
        else:
            try:
                contract_index = int(search_request.value)
            except:  # noqa: E722
                contract_index = search_request.value
            if isinstance(contract_index, str):
                url = f"/{search_request.net}/tokens/{contract_index}"
            else:
                contract_index = search_request.value
                token_id = "_"
                url = f"/{search_request.net}/token/{contract_index}/0/{token_id}"

    if url:
        response = RedirectResponse(url=url, status_code=200)
        # note do not remove this header! Very strange things will happen.
        # The new route is requested, however the browser page remains the same!
        response.headers["HX-Redirect"] = url
        return response


class SearchPlaceholderRequest(BaseModel):
    net: str
    search_selector: str


@router.post(
    "/search_placeholder",
    response_class=Response,
)
async def search_placeholder(
    request: Request,
    placeholder_request: SearchPlaceholderRequest,
):
    search_selector = placeholder_request.search_selector
    if search_selector == "all":
        return "Search ..."
    if search_selector == "block":
        return "Search for Block height or hash"
    if search_selector == "transaction":
        return "Search for Tx hash"
    if search_selector == "account":
        return "Search for account index or address"
    if search_selector == "contract":
        return "Search for contract index"
    if search_selector == "module":
        return "Search for module hash"
    if search_selector == "token":
        return '"contract_index-token_id"'


@router.get("/tmp/{filename}", response_class=FileResponse)
async def tmp_files(request: Request, filename: str):
    file_path = f"/tmp/{filename}"

    # Check if the file exists
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return FileResponse(file_path, headers=headers, media_type="text/csv")


@router.post(
    "/home_tx_graph",
    response_class=Response,
)
async def home_tx_graph(
    request: Request,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    theme = "dark"
    body = await request.body()
    if body:
        theme = body.decode("utf-8").split("=")[1]
    today = f"{dt.datetime.now().astimezone(tz=dt.timezone.utc):%Y-%m-%d}"

    minus_6m = f"{dt.datetime.now().astimezone(tz=dt.timezone.utc)-dt.timedelta(weeks=26):%Y-%m-%d}"
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/mainnet/misc/tx-data/all/{minus_6m}/{today}",
        httpx_client,
    )
    all_data = api_result.return_value if api_result.ok else None
    if not all_data:
        error = "Request error getting tx data.."
        return templates.TemplateResponse(
            "base/error.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": "mainnet",
            },
        )

    df = pd.json_normalize(all_data)
    df["sum_all"] = df.sum(axis=1, numeric_only=True)
    pass
    df["date"] = pd.to_datetime(df["date"])
    rng = ["#3EB7E5"]
    fig = px.scatter(
        df,
        x="date",
        y=df["sum_all"],
        # y=signal.savgol_filter(
        #     df["sum_all"], 60, 2  # window size used for filtering
        # ),  # order of fitted polynomial,
        color_discrete_sequence=rng,
        template=ccdexplorer_plotly_template(theme),
    )
    fig.update_yaxes(
        title_text=None,
        showgrid=False,
        linewidth=0,
        zerolinecolor="rgba(0,0,0,0)",
    )
    fig.update_traces(mode="lines")
    fig.update_xaxes(
        title=None,
        type="date",
        showgrid=False,
        linewidth=0,
        zerolinecolor="rgba(0,0,0,0)",
    )
    fig.update_layout(
        height=135,
        # width=320,
        margin=dict(l=0, r=0, t=0, b=0),
    )
    if "last_requests" not in request.state._state:
        request.state.last_requests = {}
    html = fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )
    request.state.last_requests["txs_graph"] = html
    return html


@router.get("/{net}/ajax_last_blocks", response_class=HTMLResponse)
async def ajax_last_blocks(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    if net not in ["mainnet", "testnet"]:
        return RedirectResponse(url="/mainnet", status_code=302)

    user: UserV2 = await get_user_detailsv2(request)
    latest_blocks = request.app.blocks_cache.get(net)
    if not latest_blocks:
        error = f"Request error getting the most recent blocks on {net}."
        return templates.TemplateResponse(
            "base/error-request.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )

    result = [CCD_BlockInfo(**x) for x in latest_blocks[:10]]
    if "last_requests" not in request.state._state:
        request.state.last_requests = {}
    html = templates.TemplateResponse(
        "home/last_blocks_table.html",
        {
            "request": request,
            "blocks": result,
            "net": net,
            "tags": tags,
            "user": user,
        },
    )
    request.state.last_requests["blocks"] = html
    return html


@router.get("/{net}/ajax_last_transactions", response_class=HTMLResponse)
async def ajax_last_txs(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    if net not in ["mainnet", "testnet"]:
        return RedirectResponse(url="/mainnet", status_code=302)

    user: UserV2 = await get_user_detailsv2(request)
    # api_result = await get_url_from_api(
    #     f"{request.app.api_url}/v2/{net}/transactions/last/10", httpx_client
    # )
    # latest_txs = api_result.return_value if api_result.ok else None
    latest_txs = request.app.transactions_cache.get(net)
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

    result = [CCD_BlockItemSummary(**x) for x in latest_txs[:10]]
    if "last_requests" not in request.state._state:
        request.state.last_requests = {}
    html = templates.TemplateResponse(
        "home/last_txs_table.html",
        {
            "request": request,
            "tx_type_translation": tx_type_translation,
            "txs": result,
            "net": net,
            "tags": tags,
            "user": user,
        },
    )

    request.state.last_requests["txs"] = html
    return html


@router.get("/{net}/ajax_last_transactions_own_page", response_class=HTMLResponse)
async def ajax_last_txs_own_page(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    if net not in ["mainnet", "testnet"]:
        return RedirectResponse(url="/mainnet", status_code=302)

    user: UserV2 = await get_user_detailsv2(request)
    # api_result = await get_url_from_api(
    #     f"{request.app.api_url}/v2/{net}/transactions/last/50", httpx_client
    # )
    # latest_blocks = api_result.return_value if api_result.ok else None
    latest_txs = request.app.transactions_cache.get(net)
    if not latest_txs:
        error = f"Request error getting the most recent transactions on {net}."
        return templates.TemplateResponse(
            "base/error.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )

    result = [CCD_BlockItemSummary(**x) for x in latest_txs]
    if "last_requests" not in request.state._state:
        request.state.last_requests = {}
    html = templates.TemplateResponse(
        "home/last_txs_table_own_page.html",
        {
            "request": request,
            "tx_type_translation": tx_type_translation,
            "txs": result,
            "net": net,
            "tags": tags,
            "user": user,
        },
    )

    request.state.last_requests["txs"] = html
    return html


@router.get("/{net}/ajax_last_blocks_own_page", response_class=HTMLResponse)
async def ajax_last_blocks_own_page(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    if net not in ["mainnet", "testnet"]:
        return RedirectResponse(url="/mainnet", status_code=302)

    user: UserV2 = await get_user_detailsv2(request)
    latest_blocks = request.app.blocks_cache.get(net)
    if not latest_blocks:
        error = f"Request error getting the most recent blocks on {net}."
        return templates.TemplateResponse(
            "base/error.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )

    result = [CCD_BlockInfo(**x) for x in latest_blocks]
    if "last_requests" not in request.state._state:
        request.state.last_requests = {}
    html = templates.TemplateResponse(
        "home/last_blocks_table_own_page.html",
        {
            "request": request,
            "blocks": result,
            "net": net,
            "tags": tags,
            "user": user,
        },
    )
    request.state.last_requests["blocks"] = html
    return html


@router.get("/{net}/ajax_last_accounts_own_page", response_class=HTMLResponse)
async def ajax_last_accounts_own_page(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    if net not in ["mainnet", "testnet"]:
        return RedirectResponse(url="/mainnet", status_code=302)

    user: UserV2 = await get_user_detailsv2(request)
    # print(list(request.app.addresses_to_indexes.get(net).values())[:10])
    # api_result = await get_url_from_api(
    #     f"{request.app.api_url}/v2/{net}/accounts/last/50", httpx_client
    # )
    # latest_accounts = api_result.return_value if api_result.ok else None
    latest_accounts = request.app.accounts_cache.get(net)
    # api_result = await get_url_from_api(
    #     f"{request.app.api_url}/v2/{net}/misc/identity-providers",
    #     httpx_client,
    # )
    # identity_providers = api_result.return_value if api_result.ok else None
    identity_providers = request.app.identity_providers_cache.get(net)
    if not latest_accounts:
        error = f"Request error getting the most recent accounts on {net}."
        return templates.TemplateResponse(
            "base/error.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )

    result = [
        {
            "account_info": CCD_AccountInfo(**x["account_info"]),
            "identity": Identity(CCD_AccountInfo(**x["account_info"])),
            "deployment_tx": CCD_BlockItemSummary(**x["deployment_tx"]),
        }
        for x in latest_accounts
    ]
    if "last_requests" not in request.state._state:
        request.state.last_requests = {}
    html = templates.TemplateResponse(
        "home/last_accounts_table_own_page.html",
        {
            "request": request,
            "accounts": result,
            "net": net,
            "identity_providers": identity_providers,
            "tags": tags,
            "user": user,
        },
    )
    request.state.last_requests["blocks"] = html
    return html


@router.get("/{net}/transactions", response_class=HTMLResponse)
async def transactions_page(
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
        "home/transactions.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "net": net,
            "API_KEY": request.app.env["CCDEXPLORER_API_KEY"],
        },
    )


@router.get("/{net}/blocks", response_class=HTMLResponse)
async def blocks_page(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
) -> HTMLResponse:
    if net not in ["mainnet", "testnet"]:
        return RedirectResponse(url="/mainnet", status_code=302)

    user: UserV2 = await get_user_detailsv2(request)
    request.state.api_calls = {}
    request.state.api_calls["Latest Blocks"] = (
        f"{request.app.api_url}/docs#/Blocks/get_last_blocks_v2__net__blocks_last__count__get"
    )

    return templates.TemplateResponse(
        "home/blocks.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "net": net,
            "API_KEY": request.app.env["CCDEXPLORER_API_KEY"],
        },
    )


@router.get("/{net}/accounts", response_class=HTMLResponse)
async def accounts_page(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
) -> HTMLResponse:
    if net not in ["mainnet", "testnet"]:
        return RedirectResponse(url="/mainnet", status_code=302)

    user: UserV2 = await get_user_detailsv2(request)
    request.state.api_calls = {}
    request.state.api_calls["Latest Accounts"] = (
        f"{request.app.api_url}/docs#/Accounts/get_last_accounts_v2__net__accounts_last__count__get"
    )
    return templates.TemplateResponse(
        "home/accounts.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "net": net,
            "API_KEY": request.app.env["CCDEXPLORER_API_KEY"],
        },
    )


@router.get("/{net}/ajax_consensus_own_page", response_class=HTMLResponse)
async def ajax_consensus_own_page(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    if net not in ["mainnet", "testnet"]:
        return RedirectResponse(url="/mainnet", status_code=302)

    user: UserV2 = await get_user_detailsv2(request)
    try:
        latest_consensus = CCD_ConsensusDetailedStatus(
            **request.app.consensus_cache.get(net)
        )
    except:  # noqa: E722
        latest_consensus = None

    if not latest_consensus:
        error = (
            f"Request error getting the most recent consensus detailed status on {net}."
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
    latest_consensus.epoch_bakers = None
    if "last_requests" not in request.state._state:
        request.state.last_requests = {}
    html = templates.TemplateResponse(
        "home/last_consensus_own_page.html",
        {
            "request": request,
            "consensus": latest_consensus,
            "net": net,
            "tags": tags,
            "user": user,
        },
    )
    request.state.last_requests["blocks"] = html
    return html


@router.get("/{net}/consensus", response_class=HTMLResponse)
async def consensus_page(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
) -> HTMLResponse:
    if net not in ["mainnet", "testnet"]:
        return RedirectResponse(url="/mainnet", status_code=302)

    user: UserV2 = await get_user_detailsv2(request)
    request.state.api_calls = {}
    request.state.api_calls["Consensus Detailed Status"] = (
        f"{request.app.api_url}/docs#/Misc/get_consensus_detailed_status_v2__net__misc_consensus_detailed_status_get"
    )
    return templates.TemplateResponse(
        "home/consensus.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "net": net,
            "API_KEY": request.app.env["CCDEXPLORER_API_KEY"],
        },
    )


@router.get("/misc/release-notes", response_class=HTMLResponse)
async def release_notes(
    request: Request,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/misc/release-notes",
        httpx_client,
    )
    release_notes = api_result.return_value if api_result.ok else []
    request.state.api_calls = {}
    request.state.api_calls["Release Notes"] = (
        f"{request.app.api_url}/docs#/Misc/get_release_notes_v2_misc_release_notes_get"
    )
    return templates.TemplateResponse(
        "base/release_notes.html",
        {"env": request.app.env, "request": request, "release_notes": release_notes},
    )


@router.get("/misc/privacy-policy", response_class=HTMLResponse)
async def privacy_policy(
    request: Request,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    request.state.api_calls = {}
    request.state.api_calls["None"] = ""
    return templates.TemplateResponse(
        "base/privacy_policy.html",
        {"env": request.app.env, "request": request},
    )


@router.get("/misc/support", response_class=HTMLResponse)
async def support_explorer(
    request: Request,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    request.state.api_calls = {}
    request.state.api_calls["None"] = ""
    return templates.TemplateResponse(
        "base/support.html",
        {
            "env": request.app.env,
            "request": request,
            "donations_account_id": "3cunMsEt2M3o9Rwgs2pNdsCWZKB5MkhcVbQheFHrvjjcRLSoGP",
        },
    )
