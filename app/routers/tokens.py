# ruff: noqa: F403, F405, E402, E501, E722, F401
import requests
from ccdexplorer_fundamentals.cis import (
    MongoTypeLoggedEvent,
    MongoTypeTokenAddress,
)
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_TokenId,
    CCD_TokenInfo,
    CCD_BlockInfo,
    CCD_BlockItemSummary,
    CCD_ContractAddress,
)
from pydantic import BaseModel
from ccdexplorer_fundamentals.mongodb import (
    Collections,
)
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pymongo import DESCENDING
from app.classes.dressingroom import MakeUp, MakeUpRequest, RequestingRoute
from app.env import *
from app.jinja2_helpers import *
from app.state import *

router = APIRouter()


class TokenAddress(BaseModel):
    contract: CCD_ContractAddress
    tokenID: str | None = None

    def to_str(self):
        return f"{self.contract.to_str()}-{self.tokenID}"

    @classmethod
    def from_str(cls, str_repr: str):
        """
        Returns a TokenAddress when the input is formed as '<2350,0>-xxx'.
        """
        contract_string = str_repr.split("-")[0]
        tokenID_string = str_repr.split("-")[1]
        c = CCD_ContractAddress(
            **{
                "index": contract_string.split(",")[0][1:],
                "subindex": contract_string.split(",")[1][:-1],
            }
        )

        return TokenAddress(**{"contract": c, "tokenID": tokenID_string})

    @classmethod
    def from_index(cls, index: int, subindex: int):
        s = CCD_ContractAddress(**{"index": index, "subindex": subindex})
        return s


def split_token_address(token_address: str) -> tuple[str, str]:
    contract = token_address.split("-")[0]
    token_id = token_address.split("-")[1]
    return (contract, token_id)


@router.get("/{net}/ajax_token_metadata_display/{url}")  # type:ignore
async def tokens_tag_metadata(
    request: Request,
    net: str,
    url: str,
    tags: dict = Depends(get_labeled_accounts),
):
    response = requests.get(url)
    if response.status_code == 200:
        return response


@router.get("/{net}/fungible-tokens/tvl")  # type:ignore
async def tokens_fungible_tvl(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
):
    user: UserV2 = get_user_detailsv2(request)
    return templates.TemplateResponse(
        "tokens/tokens_tvl.html",
        {
            "env": request.app.env,
            "request": request,
            "net": net,
            "user": user,
            "tags": tags,
            "token_address": "<9390,0>-",
        },
    )


# @router.get("/{net}/cis-2-tokens")  # type:ignore
@router.get("/{net}/tokens")  # type:ignore
async def slash_tokens(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/plts/overview",
        request.app.httpx_client,
    )
    plts = api_result.return_value if api_result.ok else []

    user: UserV2 | None = await get_user_detailsv2(request)
    fungible_tokens_verified = None
    non_fungible_tokens_verified = None
    if net == "mainnet":
        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/tokens/fungible-tokens/verified",
            request.app.httpx_client,
        )
        fungible_tokens_verified = api_result.return_value if api_result.ok else None
        if fungible_tokens_verified:
            fungible_tokens_verified = sorted(
                fungible_tokens_verified,
                key=lambda x: x["token_value_USD"],
                reverse=True,
            )

        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/tokens/non-fungible-tokens/verified",
            request.app.httpx_client,
        )
        non_fungible_tokens_verified = (
            api_result.return_value if api_result.ok else None
        )
    request.state.api_calls = {}
    request.state.api_calls["Fungible Tokens"] = (
        f"{request.app.api_url}/docs#/Tokens/get_fungible_tokens_verified_v2__net__tokens_fungible_tokens_verified_get"
    )
    request.state.api_calls["Non-Fungible Tokens"] = (
        f"{request.app.api_url}/docs#/Tokens/get_non_fungible_tokens_verified_v2__net__tokens_non_fungible_tokens_verified_get"
    )
    return templates.TemplateResponse(
        "tokens/tokens.html",
        {
            "env": request.app.env,
            "request": request,
            "net": net,
            "user": user,
            "tags": tags,
            "fungible_tokens_verified": fungible_tokens_verified,
            "non_fungible_tokens_verified": non_fungible_tokens_verified,
            "plts": plts,
        },
    )


@router.get(
    "/ajax_logged_events_for_token_address/{net}/{token_address_str}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def ajax_logged_events_for_token_address(
    request: Request,
    net: str,
    token_address_str: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    tags: dict = Depends(get_labeled_accounts),
):
    limit = 20
    token_address_str = token_address_str.replace("&lt;", "<").replace("&gt;", ">")

    user: UserV2 = get_user_detailsv2(request)
    typed_tokens_tag = None
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    motor_db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    stored_token_address = db_to_use[Collections.tokens_token_addresses_v2].find_one(
        {"_id": token_address_str}
    )
    typed_token_address = TokenAddress.from_str(token_address_str)
    if stored_token_address:
        stored_token_address = MongoTypeTokenAddress(**stored_token_address)
        typed_tokens_tag = token_tag_if_exists(typed_token_address.contract, db_to_use)
        metadata = None
        if not typed_tokens_tag:
            metadata = retrieve_metadata_for_stored_token_address(
                token_address_str, db_to_use
            )

    if requested_page > -1:
        skip = requested_page * limit
    else:
        nr_of_pages, _ = divmod(total_rows, limit)
        skip = nr_of_pages * limit

    metadata = None
    decimals = 0 if not typed_tokens_tag else typed_tokens_tag.decimals
    if not typed_tokens_tag:
        metadata = retrieve_metadata_for_stored_token_address(
            token_address_str, db_to_use
        )
        if metadata:
            decimals = metadata.decimals

    pipeline = [
        {"$match": {"token_address": token_address_str}},
        {
            "$sort": {
                "block_height": DESCENDING,
                "tx_index": DESCENDING,
                "ordering": DESCENDING,
            }
        },
        {
            "$facet": {
                "metadata": [{"$count": "total"}],
                "data": [{"$skip": skip}, {"$limit": limit}],
            }
        },
        {
            "$project": {
                "data": 1,
                "total": {"$arrayElemAt": ["$metadata.total", 0]},
            }
        },
    ]
    result = (
        await motor_db_to_use[Collections.tokens_logged_events]
        .aggregate(pipeline)
        .to_list(limit)
    )

    logged_events = [MongoTypeLoggedEvent(**x) for x in result[0]["data"]]
    for event in logged_events:
        event.slot_time = CCD_BlockInfo(
            **db_to_use[Collections.blocks].find_one({"height": event.block_height})
        ).slot_time

    if "total" in result[0]:
        total_event_count = result[0]["total"]
    else:
        total_event_count = 0

    # logged_events = [
    #     MongoTypeLoggedEvent(**x)
    #     for x in db_to_use[Collections.tokens_logged_events]
    #     .find({"token_address": token_address})
    #     .sort(
    #         [
    #             ("block_height", DESCENDING),
    #             ("tx_index", DESCENDING),
    #             ("ordering", DESCENDING),
    #         ]
    #     )
    #     .skip(skip)
    #     .limit(limit)
    # ]
    html = process_logged_events_to_HTML_v2(
        request,
        logged_events,
        total_event_count,
        requested_page,
        user,
        tags,
        net,
        metadata,
        typed_tokens_tag,
        decimals,
    )
    return html


@router.get(
    "/ajax_token_ids_for_tag_single_use/{net}/{tag}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def ajax_token_ids_for_tag(
    request: Request,
    net: str,
    tag: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    tags: dict = Depends(get_labeled_accounts),
):
    limit = 20
    # token_address_str = token_address_str.replace("&lt;", "<").replace("&gt;", ">")
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    # motor_db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    metadata = None
    stored_tag = db_to_use[Collections.tokens_tags].find_one({"_id": tag})
    is_PTRT = tag == "PTRT"
    if not stored_tag:
        return None

    pipeline = [
        {"$match": {"contract": {"$in": stored_tag["contracts"]}}},
        {"$match": {"hidden": False}},
    ]
    result = list(db_to_use[Collections.tokens_token_addresses_v2].aggregate(pipeline))
    token_address_for_tag = None
    if len(result) > 0:
        token_address_for_tag = MongoTypeTokenAddress(**result[0])

    metadata = find_token_address_from_contract_address(
        db_to_use, stored_tag["contracts"][0]
    )
    pipeline = [
        {"$match": {"token_holding.token_address": token_address_for_tag.id}},
        {"$match": {"token_holding.token_amount": {"$regex": "-"}}},
        {"$limit": 1},
    ]

    any_faulty_holdings = list(
        db_to_use[Collections.tokens_links_v2].aggregate(pipeline)
    )
    non_compliant_contract = len(any_faulty_holdings) > 0
    return templates.TemplateResponse(
        "tokens/generic/token_display_fungible.html",
        {
            "env": request.app.env,
            "request": request,
            "is_PTRT": is_PTRT,
            "net": net,
            "non_compliant_contract": non_compliant_contract,
            "contract": (
                token_address_for_tag.contract
                if token_address_for_tag
                else stored_tag["contracts"][0]
            ),
            "token_address_result": (
                token_address_for_tag
                if token_address_for_tag
                else {"id": f"{stored_tag['contracts'][0]}-unknown"}
            ),
            "metadata": metadata,
            "token_id": (
                token_address_for_tag.token_id if token_address_for_tag else "unknown"
            ),
            "tag": tag,
            "stored_tag": stored_tag,
            "user": user,
            "tags": tags,
        },
    )


@router.get(
    "/{net}/ajax_nft_tokens_for/{tag}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def ajax_nft_tokens_for_tag(
    request: Request,
    net: str,
    tag: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    limit = 10
    skip = calculate_skip(requested_page, total_rows, limit)
    user: UserV2 | None = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/token/tag/{tag}/{skip}/{limit}",
        httpx_client,
    )
    nft_tokens = api_result.return_value if api_result.ok else None

    pagination_request = PaginationRequest(
        total_txs=total_rows,
        requested_page=requested_page,
        word="token",
        action_string="nft_token",
        limit=limit,
        returned_rows=len(nft_tokens),
    )
    pagination = pagination_calculator(pagination_request)
    request.state.api_calls = {}
    request.state.api_calls["NFT Tokens"] = (
        f"{request.app.api_url}/docs#/Token/get_nft_tag_tokens_v2__net__token_tag__tag___skip___limit__get"
    )
    html = templates.get_template("tokens/nft_tag/nft_tag_tokens.html").render(
        {
            "nft_tokens": nft_tokens,
            "tags": tags,
            "tag": tag,
            "net": net,
            "request": request,
            "pagination": pagination,
            "total_rows": total_rows,
        }
    )

    return html


# @router.get(
#     "/ajax_statistics_tvl/{token_address}",
#     response_class=Response,
# )
# async def statistics_token_TVL_plotly(
#     request: Request,
#     token_address: str,
# ):
#     analysis = "statistics_tvl_for_tokens"

#     token_address = token_address.replace("&lt;", "<").replace("&gt;", ">")
#     all_data = get_all_data_for_analysis_for_token(analysis, token_address, mongodb)
#     d_date = get_statistics_date(mongodb)
#     df = pd.DataFrame(all_data)
#     df["tvl"] = df["tvl_contribution_for_day_in_usd"].cumsum()
#     rng = ["#70B785"]
#     title = "EUROe"
#     fig = px.line(
#         df,
#         x="date",
#         y="tvl",
#         color_discrete_sequence=rng,
#         template=ccdexplorer_plotly_template(),
#     )
#     fig.update_yaxes(title_text="TVL")
#     fig.update_xaxes(title=None)
#     fig.update_layout(
#         legend_title_text=title,
#         title=f"<b>{title}</b><br><sup>{d_date}</sup>",
#         height=550,
#     )
#     return fig.to_html(
#         config={"responsive": True, "displayModeBar": False},
#         full_html=False,
#         include_plotlyjs=False,
#     )


@router.get("/{net}/token/{contract_index}/{contract_subindex}")
@router.get(
    "/{net}/token/{contract_index}/{contract_subindex}/{token_id}"
)  # type:ignore
async def get_token_token_address(
    request: Request,
    net: str,
    contract_index: int,
    contract_subindex: int,
    token_id: Optional[str] = "_",
    tags: dict = Depends(get_labeled_accounts),
):
    # user: UserV2 | None = await get_user_detailsv2(request)
    token_id = token_id.lower()
    contract = CCD_ContractAddress.from_index(contract_index, contract_subindex)

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/token/{contract.index}/{contract.subindex}/{token_id}/info",
        request.app.httpx_client,
    )
    stored_token_address = api_result.return_value if api_result.ok else None
    og_title = f"Token {token_id} from smart contract ({contract.index}, {contract.subindex}) on Concordium {net}"
    return await show_token_address(
        request,
        net,
        stored_token_address,
        contract_index,
        contract_subindex,
        token_id,
        tags,
        og_title,
    )


async def show_token_address(
    request: Request,
    net: str,
    stored_token_address: dict,
    contract_index: str,
    contract_subindex: str,
    token_id: str,
    tags: dict,
    og_title: str,
):
    """Only for fungible tags and indivitual token addresses, not non-fungible tags"""
    user: UserV2 | None = await get_user_detailsv2(request)

    if not stored_token_address:
        error = f"Can't find the token at {contract_index}/{contract_subindex}/{token_id} on {net}."
        return templates.TemplateResponse(
            "base/error.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )
    contract = CCD_ContractAddress.from_index(contract_index, contract_subindex)

    # CIS-2 compliant?
    use_token_id = "_" if token_id == "" else token_id
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/token/{contract_index}/{contract_subindex}/{use_token_id}/cis-2-compliant",
        request.app.httpx_client,
    )
    compliant_contract = api_result.return_value if api_result.ok else True

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/transaction/{stored_token_address["mint_tx_hash"]}",
        request.app.httpx_client,
    )
    tx_deployed = (
        CCD_BlockItemSummary(**api_result.return_value) if api_result.ok else None
    )
    request.state.api_calls = {}
    request.state.api_calls["Token Info"] = (
        f"{request.app.api_url}/docs#/Token/get_info_for_token_address_v2__net__token__contract_index___contract_subindex___token_id__info_get"
    )
    request.state.api_calls["Token Mint Tx"] = (
        f"{request.app.api_url}/docs#/Transaction/get_transaction_v2__net__transaction__tx_hash__get"
    )
    template_dict = {
        "env": request.app.env,
        "request": request,
        "net": net,
        "contract": contract,
        "tx_deployed": tx_deployed,
        "stored_token_address": stored_token_address,
        "token_id": token_id,
        "compliant_contract": compliant_contract,
        # "stored_tag": tokens_tag,
        # "is_PTRT": False,
        # "tag": tag,
        "user": user,
        "tags": tags,
        "ogp_title": og_title,
        "ogp_url": request.url._url,
        # "owner_history_list": owner_history_list,
    }

    return templates.TemplateResponse(
        "tokens/generic/token_address_display.html", template_dict
    )


@router.get(
    "/ajax_plt_tokens/{net}/{token_id}",
    response_class=HTMLResponse,
)
async def get_plt_token_holders_paginated(
    request: Request,
    net: str,
    token_id: str,
    page: int = Query(),
    size: int = Query(),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
    tags: dict = Depends(get_labeled_accounts),
    # recurring: Recurring = Depends(get_recurring),
):
    user: UserV2 | None = await get_user_detailsv2(request)
    skip = (page - 1) * size
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/plt/{token_id}/holders/{skip}/{size}",
        httpx_client,
    )
    holders = api_result.return_value if api_result.ok else {}
    if not holders:
        error = f"Request error getting holders for token at {token_id} on {net}."
        return templates.TemplateResponse(
            "base/error-request.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )

    holders_data = holders["data"]

    tb_made_up_rows = []

    if token_id in request.app.plt_cache[net]:
        decimals = request.app.plt_cache[net][token_id].get("decimals", 0)
    else:
        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/plt/{token_id}/info",
            request.app.httpx_client,
        )
        plt_info = api_result.return_value if api_result.ok else None
        plt_info = CCD_TokenInfo(**plt_info) if plt_info else None
        decimals = plt_info.token_state.decimals if plt_info else 0

    for row in holders_data:
        sender = account_link(
            row["account_address"],
            net,
            user=user,
            tags=tags,
            app=request.app,
        )
        tb_made_up_rows.append(
            create_dict_for_tabulator_display_for_plt_token_holders(
                net, user, request.app, tags, row, sender, decimals
            )
        )
    total_rows = holders["total_row_count"]  # type: ignore
    last_page = math.ceil(total_rows / size)
    return JSONResponse(
        {
            "data": tb_made_up_rows,
            "last_page": max(1, last_page),
            "last_row": total_rows,
        }
    )


class SortItem(BaseModel):
    field: str
    dir: str


class FilterItem(BaseModel):
    field: str
    type: str
    value: str


class TabulatorRequest(BaseModel):
    page: int
    size: int
    sort: Optional[list[SortItem]] = []
    filter: Optional[list[FilterItem]] = []


@router.post(
    "/ajax_plt_token_transactions/{net}/{token_id}",
    response_class=HTMLResponse,
)
async def get_plt_transactions_for_tabulator(
    request: Request,
    net: str,
    token_id: str,
    body: TabulatorRequest,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
    # recurring: Recurring = Depends(get_recurring),
    tags: dict = Depends(get_labeled_accounts),
):
    """
    Transactions for plt.
    """

    user: UserV2 | None = await get_user_detailsv2(request)

    skip = (body.page - 1) * body.size

    if body.sort and len(body.sort) > 0:
        sort_key = body.sort[0].field
        direction = body.sort[0].dir
    else:
        sort_key = "block_height"
        direction = "desc"

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/plt/{token_id}/transactions/{skip}/{body.size}/{sort_key}/{direction}",
        httpx_client,
    )
    tx_result = api_result.return_value if api_result.ok else None
    if not tx_result:
        error = f"Request error getting transactions for plt at {token_id} on {net}."
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
        tb_made_up_txs = []
        tx_result_transactions = tx_result["transactions"]

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

                type_additional_info, sender = (
                    await classified_tx.transform_for_tabulator(plt_page=True)
                )

                tb_made_up_txs.append(
                    create_dict_for_tabulator_display_plt_transactions(
                        net, classified_tx, type_additional_info, sender
                    )
                )
        total_rows = tx_result["total_tx_count"]
        last_page = math.ceil(total_rows / body.size)
        return JSONResponse(
            {
                "data": tb_made_up_txs,
                "last_page": max(1, last_page),
                "last_row": total_rows,
            }
        )


async def show_plt(
    request: Request,
    net: str,
    token_id: str,
):
    """Only for PLTs"""
    user: UserV2 | None = await get_user_detailsv2(request)
    og_title = f"PLT {token_id} on Concordium {net}"

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/plt/{token_id}/info",
        request.app.httpx_client,
    )
    plt_info = api_result.return_value if api_result.ok else None
    plt_info = CCD_TokenInfo(**plt_info) if plt_info else None

    template_dict = {
        "env": request.app.env,
        "request": request,
        "net": net,
        "token_id": token_id,
        "plt_info": plt_info,
        "user": user,
        "ogp_title": og_title,
        "ogp_url": request.url._url,
        "tx_type_translation_from_python": tx_type_translation_for_js(),
        # "owner_history_list": owner_history_list,
    }

    return templates.TemplateResponse("tokens/plt/plt_display.html", template_dict)


async def show_nft_tag(request: Request, net: str, tag_result: dict):
    """Only for non-fungible tags"""
    user: UserV2 | None = await get_user_detailsv2(request)

    template_dict = {
        "env": request.app.env,
        "request": request,
        "net": net,
        "user": user,
        "vi": tag_result,
    }

    return templates.TemplateResponse(
        "tokens/nft_tag/nft_tag_display.html", template_dict
    )


@router.get("/{net}/tokens/{tag}")
@router.get("/{net}/tokens/{tag}/{token_id_or_address}")  # type:ignore
async def tokens_tag_token_id(
    request: Request,
    net: str,
    tag: str,
    token_id_or_address: Optional[str] = None,
    tags: dict = Depends(get_labeled_accounts),
):
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/plt/list-token-ids",
        request.app.httpx_client,
    )
    plts: list[CCD_TokenId] = api_result.return_value if api_result.ok else []  # type: ignore

    if tag in plts:
        return await show_plt(
            request,
            net,
            tag,
        )

    og_title = ""
    if tag == "_":
        splits = token_id_or_address.split("-")
        contract = CCD_ContractAddress.from_str(splits[0])
        contract_index = contract.index
        contract_subindex = contract.subindex
        token_id = splits[1]

        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/token/{contract.index}/{contract.subindex}/{token_id}/info",
            request.app.httpx_client,
        )
        stored_token_address = api_result.return_value if api_result.ok else None
        og_title = f"Token {token_id} from smart contract ({contract.index}, {contract.subindex}) on Concordium {net}"
    else:
        # first request the tag
        # if tag is fungible, continue here.
        # if tag is non-fungible, go to separate function to display NFT tag.
        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/token/{tag}/info",
            request.app.httpx_client,
        )
        tag_result = api_result.return_value if api_result.ok else None

        if tag_result and not token_id_or_address:
            if tag_result["token_type"] == "non-fungible":
                print("NFT")
                return await show_nft_tag(request, net, tag_result)

        # continue here with fungible or unknown tag.

        if token_id_or_address:
            # non-fungible token
            token_id = token_id_or_address.lower()
            api_result = await get_url_from_api(
                f"{request.app.api_url}/v2/{net}/token/tag/{tag}/token-id/{token_id}/info",
                request.app.httpx_client,
            )
            stored_token_address = api_result.return_value if api_result.ok else None
            og_title = f"Non-Fungible Token {token_id} from {tag} on Concordium {net}"
        else:
            # fungible token
            token_id = ""
            api_result = await get_url_from_api(
                f"{request.app.api_url}/v2/{net}/token/tag/{tag}/info",
                request.app.httpx_client,
            )
            stored_token_address = api_result.return_value if api_result.ok else None
            og_title = f"Fungible Token {tag} on Concordium {net}"
        if stored_token_address:
            contract = CCD_ContractAddress.from_str(stored_token_address["contract"])
            contract_index = contract.index
            contract_subindex = contract.subindex
        else:
            contract_index = 0
            contract_subindex = 0
            if not stored_token_address:
                if not token_id_or_address:
                    error = f"Can't find the token at {tag} on {net}."
                else:
                    error = (
                        f"Can't find the token at {tag}-{token_id_or_address} on {net}."
                    )
                return templates.TemplateResponse(
                    "base/error.html",
                    {
                        "request": request,
                        "error": error,
                        "env": environment,
                        "net": net,
                    },
                )

    return await show_token_address(
        request,
        net,
        stored_token_address,
        contract_index,
        contract_subindex,
        token_id,
        tags,
        og_title,
    )


@router.get(
    "/{net}/token/{contract_index}/{contract_subindex}/{token_id}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def get_token_current_holders(
    request: Request,
    net: str,
    contract_index: int,
    contract_subindex: int,
    token_id: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
    tags: dict = Depends(get_labeled_accounts),
):
    user: UserV2 | None = await get_user_detailsv2(request)
    limit = 10
    skip = calculate_skip(requested_page, total_rows, limit)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/token/{contract_index}/{contract_subindex}/{token_id}/info",
        request.app.httpx_client,
    )
    stored_token_address = api_result.return_value if api_result.ok else None
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/token/{contract_index}/{contract_subindex}/{token_id}/holders/{skip}/{limit}",
        httpx_client,
    )
    current_holders = (
        api_result.return_value["current_holders"] if api_result.ok else None
    )
    total_rows = api_result.return_value["total_count"] if api_result.ok else None
    pagination_request = PaginationRequest(
        total_txs=total_rows,
        requested_page=requested_page,
        word="holder",
        action_string="holder",
        limit=limit,
    )
    pagination = pagination_calculator(pagination_request)

    curren_holder_with_id = current_holders

    current_holders = []
    for holder in curren_holder_with_id:
        if "-" in holder["account_address_canonical"]:
            address_to_lookup = holder["account_address_canonical"].split("-")[1]
        else:
            address_to_lookup = holder["account_address_canonical"]
        holder.update(
            {
                "account_index": from_address_to_index(
                    address_to_lookup, net, request.app
                )
            }
        )
        current_holders.append(holder)

    html = templates.get_template("tokens/generic/token_current_holders.html").render(
        {
            "co": current_holders,
            "tags": tags,
            "user": user,
            "net": net,
            "request": request,
            "pagination": pagination,
            "totals_in_pagination": True,
            "total_rows": total_rows,
            "stored_token_address": stored_token_address,
        }
    )

    return html
