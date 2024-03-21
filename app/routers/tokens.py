# ruff: noqa: F403, F405, E402, E501, E722, F401

from fastapi import APIRouter, Request, Depends
from typing import Union
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from app.classes.dressingroom import MakeUp, TransactionClassifier, MakeUpRequest
import operator
from datetime import timedelta
from ccdexplorer_fundamentals.GRPCClient import GRPCClient

from app.Recurring.recurring import Recurring
from app.jinja2_helpers import *
from pymongo import ASCENDING, DESCENDING
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import *
from app.env import *
from app.state.state import *
from app.console import console
from ccdexplorer_fundamentals.tooter import Tooter, TooterType, TooterChannel
from ccdexplorer_fundamentals.cis import (
    CIS,
    TokenMetaData,
    MongoTypeLoggedEvent,
    transferEvent,
    MongoTypeTokenAddress,
)
from ccdexplorer_fundamentals.mongodb import (
    MongoDB,
    MongoMotor,
    Collections,
)
from bisect import bisect_right
from app.ajax_helpers import (
    process_transactions_to_HTML,
    transactions_html_footer,
    mongo_transactions_html_header,
    process_logged_events_to_HTML_v2,
    process_summed_rewards,
    process_token_holders_to_HTML_v2,
    process_token_ids_for_tag_to_HTML_v2,
)

router = APIRouter()


class TokenAddress(BaseModel):
    contract: CCD_ContractAddress
    tokenID: str = None

    def to_str(self):
        return f"{self.contract.to_str()}-{self.tokenID}"

    @classmethod
    def from_str(self, str_repr: str):
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
    def from_index(self, index: int, subindex: int):
        s = CCD_ContractAddress(**{"index": index, "subindex": subindex})
        return s


def split_token_address(token_address: str) -> tuple[str, str]:
    contract = token_address.split("-")[0]
    token_id = token_address.split("-")[1]
    return (contract, token_id)


@router.get(
    "/ajax_token_events/{net}/{days}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)  # type:ignore
async def ajax_token_events(
    request: Request,
    net: str,
    days: int,
    requested_page: int,
    total_rows: int,
    api_key: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
    contracts_with_tag_info: dict = Depends(get_contracts_with_tag_info),
    token_addresses_with_markup: dict = Depends(get_token_addresses_with_markup),
    credential_issuers: list = Depends(get_credential_issuers),
    ccd_historical: dict = Depends(get_exchange_rates_ccd_historical),
):
    limit = 20
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    if api_key != request.app.env["API_KEY"]:
        return "No valid api key supplied."
    else:
        now = dt.datetime.utcnow()
        cutoff = now - timedelta(days=days)

        tx_tabs: dict[TransactionClassifier, list] = {}
        tx_tabs_active: dict[TransactionClassifier, bool] = {}

        for tab in TransactionClassifier:
            tx_tabs[tab] = []

    # requested page = 0 indicated the first page
    # requested page = -1 indicates the last page
    if requested_page > -1:
        skip = requested_page * limit
    else:
        nr_of_pages, _ = divmod(total_rows, limit)
        skip = nr_of_pages * limit

    pipeline = [{"$match": {"slot_time": {"$gte": cutoff}}}]
    last_block_for_event = (
        await db_to_use[Collections.blocks].aggregate(pipeline).to_list(1)
    )
    last_block_for_event = CCD_BlockInfo(**last_block_for_event[0])
    pipeline = [
        {"$match": {"block_height": {"$gte": last_block_for_event.height}}},
        {"$sort": {"block_height": DESCENDING}},
        {
            "$facet": {
                "metadata": [{"$count": "total"}],
                # "data": [{"$skip": int(skip)}, {"$limit": int(limit)}],
                "data": [],
            }
        },
        {
            "$project": {
                "data": 1,
                "total": {"$arrayElemAt": ["$metadata.total", 0]},
            }
        },
    ]
    dd = (
        await db_to_use[Collections.tokens_logged_events]
        .aggregate(pipeline)
        .to_list(100_000)
    )
    tx_hashes = list(set([MongoTypeLoggedEvent(**x).tx_hash for x in dd[0]["data"]]))
    if "total" in dd[0]:
        total_row_count = dd[0]["total"]
    else:
        total_row_count = 0

    dd = (
        await db_to_use[Collections.transactions]
        .find({"_id": {"$in": tx_hashes}})
        .sort([("block_info.slot_time", DESCENDING)])
        .skip(skip)
        .to_list(limit)
    )
    tx_result = [CCD_BlockItemSummary(**x) for x in dd]

    if len(tx_result) > 0:
        for transaction in tx_result:
            makeup_request = MakeUpRequest(
                **{
                    "net": net,
                    "grpcclient": grpcclient,
                    "mongodb": mongodb,
                    "tags": tags,
                    "user": user,
                    "ccd_historical": ccd_historical,
                    "contracts_with_tag_info": contracts_with_tag_info,
                    "token_addresses_with_markup": token_addresses_with_markup,
                    "credential_issuers": credential_issuers,
                    "app": request.app,
                }
            )
            classified_tx = MakeUp(makeup_request=makeup_request).prepare_for_display(
                transaction, "", False
            )

            tx_tabs[classified_tx.classifier].append(classified_tx)

    tab_selected_to_be_active = False
    for tab in TransactionClassifier:
        tx_tabs_active[tab] = False
        if (not tab_selected_to_be_active) and (len(tx_tabs[tab]) > 0):
            tab_selected_to_be_active = True
            tx_tabs_active[tab] = True

    html = mongo_transactions_html_header(
        None,
        total_row_count,
        requested_page,
        tx_tabs,
        tx_tabs_active,
        block_transactions=False,
        word=f"token_event",
    )

    for tab in TransactionClassifier:
        html += process_transactions_to_HTML(
            tx_tabs[tab], tab.value, tx_tabs_active[tab], tags
        )

    html += transactions_html_footer()
    return html


def find_token_address_from_contract_address(db_to_use, contract_address: str):
    result = db_to_use[Collections.tokens_token_addresses_v2].find_one(
        {"contract": contract_address}
    )

    metadata = None
    if result:
        url = result["metadata_url"]
        try:
            r = requests.get(url)
            if r.status_code == 200:
                try:
                    metadata = TokenMetaData(**r.json())
                except Exception as e:
                    metadata = None
                    console.log(
                        f"{e}: Could not convert {r.json()} to TokenMetaData..."
                    )
        except Exception as e:
            metadata = None
            console.log(f"{e}: Could not reach {url}...")
    return metadata


def get_owner_history_for_provenance(
    grpcclient: GRPCClient,
    tokenID: str,
    contract_address: CCD_ContractAddress,
    net: NET,
):
    entrypoint = "provenance_tag_nft.view_owner_history"
    ci = CIS(
        grpcclient,
        contract_address.index,
        contract_address.subindex,
        entrypoint,
        net,
    )
    parameter_bytes = ci.viewOwnerHistoryRequest(tokenID)

    ii = grpcclient.invoke_instance(
        "last_final",
        contract_address.index,
        contract_address.subindex,
        entrypoint,
        parameter_bytes,
        net,
    )

    result = ii.success.return_value
    return ci.viewOwnerHistoryResponse(result)


@router.get(
    "/{net}/tokens-special/PTRT/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)  # type:ignore
async def token_ptrt(
    request: Request,
    net: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
):
    limit = 20
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    motor_db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet

    if requested_page > -1:
        skip = requested_page * limit
    else:
        nr_of_pages, _ = divmod(total_rows, limit)
        skip = nr_of_pages * limit

    ptrt_tokens_tag = db_to_use[Collections.tokens_tags].find_one({"_id": "PTRT"})
    ptrt_contract_for_tag = CCD_ContractAddress.from_str(
        ptrt_tokens_tag["contracts"][0]
    )

    tokens_tag = db_to_use[Collections.tokens_tags].find_one({"_id": "EUROe"})
    contract_for_tag = CCD_ContractAddress.from_str(tokens_tag["contracts"][0])
    token_address_str = f'{tokens_tag["contracts"][0]}-'
    typed_tokens_tag = token_tag_if_exists(contract_for_tag, db_to_use)
    decimals = 0 if not typed_tokens_tag else typed_tokens_tag.decimals
    metadata = None
    if not typed_tokens_tag:
        metadata = retrieve_metadata_for_stored_token_address(
            token_address_str, db_to_use
        )
        if metadata:
            decimals = metadata.decimals

    ptrt_all_tx_hashes = [
        x["_id"].split("-")[0]
        for x in db_to_use[Collections.involved_contracts].find(
            {"index": ptrt_contract_for_tag.index}, projection={"_id": 1}
        )
    ]

    # first get events for summed view
    pipeline = [
        {"$match": {"tx_hash": {"$in": ptrt_all_tx_hashes}}},
        {"$match": {"tag": 255}},
        {
            "$sort": {
                "block_height": ASCENDING,
            }
        },
    ]
    result_for_sum = (
        await motor_db_to_use[Collections.tokens_logged_events]
        .aggregate(pipeline)
        .to_list(1_000_000_000)
    )

    logged_events_for_sum = [transferEvent(**x["result"]) for x in result_for_sum]
    summed_rewards_dict = {}
    for e in logged_events_for_sum:
        if not summed_rewards_dict.get(e.to_address):
            summed_rewards_dict[e.to_address] = 0
        # if e.to_address[:4] == "41jb":
        #     print(
        #         e.to_address[:4],
        #         summed_rewards_dict[e.to_address] / 1_000_000,
        #         e.token_amount / 1_000_000,
        #         (summed_rewards_dict[e.to_address] + e.token_amount) / 1_000_000,
        #     )
        summed_rewards_dict[e.to_address] += e.token_amount

    # then get events again but using skip and limit
    pipeline = [
        {"$match": {"tx_hash": {"$in": ptrt_all_tx_hashes}}},
        {"$match": {"tag": 255}},
        {
            "$sort": {
                "block_height": DESCENDING,
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

    html = process_summed_rewards(
        request,
        summed_rewards_dict,
        user,
        tags,
        net,
        metadata,
        typed_tokens_tag,
        decimals,
    )
    html += process_logged_events_to_HTML_v2(
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
        rewards=True,
    )
    return html


@router.get("/{net}/tokens/{tag}/{token_id_or_address}")  # type:ignore
async def tokens_tag_token_id(
    request: Request,
    net: str,
    tag: str,
    token_id_or_address: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
):
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet

    # steps
    # 1. find contracts associated with tag
    # 2. create token_address
    # 3. find token_address in collection
    token_id_or_address = token_id_or_address.lower()
    metadata = None
    owner_history_list = None
    if tag == "_":
        token_address = token_id_or_address
        stored_token_address = db_to_use[
            Collections.tokens_token_addresses_v2
        ].find_one({"_id": token_address})
        typed_token_address = TokenAddress.from_str(token_address)
        contract, token_id = split_token_address(token_address)
        tokens_tag = None
    else:
        token_id = token_id_or_address

        tokens_tag = db_to_use[Collections.tokens_tags].find_one({"_id": tag})
        stored_tag = tokens_tag
        if tokens_tag:
            contracts_for_tag = tokens_tag["contracts"]
            for contract in contracts_for_tag:
                token_address = f"{contract}-{token_id_or_address}"
                stored_token_address = db_to_use[
                    Collections.tokens_token_addresses_v2
                ].find_one({"_id": token_address})
                if stored_token_address:
                    break
        else:
            stored_token_address = None
    # metadata = retrieve_metadata_for_stored_token_address(token_address, db_to_use)
    if stored_token_address:
        stored_token_address = MongoTypeTokenAddress(**stored_token_address)
        if tag == "provenance-tags":
            owner_history_list = get_owner_history_for_provenance(
                grpcclient,
                token_id,
                CCD_ContractAddress.from_str(stored_token_address.contract),
                NET(net),
            )

    template_dict = {
        "env": request.app.env,
        "request": request,
        "net": net,
        "contract": contract,
        "token_address_result": stored_token_address,
        "metadata": (
            stored_token_address.token_metadata
            if stored_token_address is not None
            else None
        ),
        "token_id": token_id,
        "stored_tag": tokens_tag,
        "is_PTRT": False,
        "tag": tag,
        "user": user,
        "tags": tags,
        "owner_history_list": owner_history_list,
    }

    if not tokens_tag:
        return templates.TemplateResponse(
            f"tokens/generic/token_display_nft.html", template_dict
        )
    else:
        if tokens_tag["tag_template"]:
            return templates.TemplateResponse(
                f"tokens/{tag}/token_display.html", template_dict
            )
        else:
            return templates.TemplateResponse(
                f"tokens/generic/token_display_nft.html", template_dict
            )


@router.get("/{net}/ajax_token_metadata_display/{url}")  # type:ignore
async def tokens_tag(
    request: Request,
    net: str,
    url: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
):
    response = requests.get(url)
    if response.status_code == 200:
        return response


@router.get("/{net}/tokens/{tag}")  # type:ignore
async def tokens_tag(
    request: Request,
    net: str,
    tag: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
):
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet

    # steps
    # 1. find contracts associated with tag
    # 2. create token_address
    # 3. find token_address in collection
    token_addresses_for_tag = []
    stored_tag = db_to_use[Collections.tokens_tags].find_one({"_id": tag})
    token_addresses_for_tag = db_to_use[Collections.tokens_token_addresses_v2].find_one(
        {"contract": stored_tag["contracts"][0]}
    )
    is_PTRT = tag == "PTRT"
    ajax_url = (
        "ajax_token_ids_for_tag_single_use"
        if stored_tag["single_use_contract"]
        else "ajax_token_ids_for_tag_multiple_use"
    )
    return templates.TemplateResponse(
        "tokens/token_overview.html",
        {
            "env": request.app.env,
            "request": request,
            "net": net,
            "user": user,
            "tags": tags,
            "tag": tag,
            "stored_tag": stored_tag,
            "token_address_result": (
                {"id": token_addresses_for_tag["_id"]}
                if token_addresses_for_tag
                else {"id": f"{stored_tag['contracts'][0]}-unknown"}
            ),
            "token_addresses_for_tag": token_addresses_for_tag,
            "ajax_url": ajax_url,
        },
    )


@router.get("/{net}/tokens")  # type:ignore
async def smart_contracts_tokens_overview(
    request: Request,
    net: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
    token_addresses_with_markup: dict = Depends(get_token_addresses_with_markup),
):
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    # motor_db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet

    tokens_tags = [
        MongoTypeTokensTag(**x)
        for x in db_to_use[Collections.tokens_tags].find(
            {"$or": [{"hidden": {"$exists": False}}, {"hidden": False}]}
        )
    ]

    logged_events_by_contract = {
        x["_id"]: x["count"]
        for x in db_to_use[Collections.pre_tokens_overview].find({})
    }

    for tt in tokens_tags:
        if tt.token_type == "fungible":
            contract = tt.contracts[0]
            token_address_with_markup: MongoTypeTokenAddress = (
                token_addresses_with_markup.get(f"{contract}-")
            )
            if token_address_with_markup:
                tvl_for_token = int(token_address_with_markup.token_amount) * (
                    math.pow(10, -token_address_with_markup.tag_information.decimals)
                )
                tvl_for_token_in_usd = (
                    tvl_for_token * token_address_with_markup.exchange_rate
                )
                tt.tvl_for_token_in_usd = tvl_for_token_in_usd
            else:
                tt.tvl_for_token_in_usd = 0
        tt.logged_events_count = 0
        for contract in tt.contracts:
            if contract in logged_events_by_contract.keys():
                tt.logged_events_count += logged_events_by_contract[contract]

    return templates.TemplateResponse(
        "tokens/tokens.html",
        {
            "env": request.app.env,
            "request": request,
            "net": net,
            "user": user,
            "tags": tags,
            "tokens_tags": tokens_tags,
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
    grpcclient: GRPCClient = Depends(get_grpcclient),
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    tags: dict = Depends(get_labeled_accounts),
):
    limit = 20
    token_address_str = token_address_str.replace("&lt;", "<").replace("&gt;", ">")

    user: UserV2 = get_user_detailsv2(request)
    typed_tokens_tag = None
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    motor_db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    if api_key != request.app.env["API_KEY"]:
        return "No valid api key supplied."
    else:
        stored_token_address = db_to_use[
            Collections.tokens_token_addresses_v2
        ].find_one({"_id": token_address_str})
        typed_token_address = TokenAddress.from_str(token_address_str)
        if stored_token_address:
            stored_token_address = MongoTypeTokenAddress(**stored_token_address)
            typed_tokens_tag = token_tag_if_exists(
                typed_token_address.contract, db_to_use
            )
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
    "/ajax_token_holders_for_token_address/{net}/{token_address_str}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def ajax_token_holders_for_token_address(
    request: Request,
    net: str,
    token_address_str: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    tags: dict = Depends(get_labeled_accounts),
):
    limit = 20
    token_address_str = token_address_str.replace("&lt;", "<").replace("&gt;", ">")
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    motor_db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    metadata = None
    typed_tokens_tag = None
    single_use_contract = False
    if api_key != request.app.env["API_KEY"]:
        return "No valid api key supplied."
    else:
        if requested_page > -1:
            skip = requested_page * limit
        else:
            nr_of_pages, _ = divmod(total_rows, limit)
            skip = nr_of_pages * limit

        stored_token_address = db_to_use[
            Collections.tokens_token_addresses_v2
        ].find_one({"_id": token_address_str})

        typed_token_address = TokenAddress.from_str(token_address_str)
        if stored_token_address:
            stored_token_address = MongoTypeTokenAddress(**stored_token_address)
            typed_tokens_tag = token_tag_if_exists(
                typed_token_address.contract, db_to_use
            )
            metadata = None
            decimals = 0 if not typed_tokens_tag else typed_tokens_tag.decimals
            if not typed_tokens_tag:
                metadata = retrieve_metadata_for_stored_token_address(
                    token_address_str, db_to_use
                )
                if metadata:
                    decimals = metadata.decimals

            token_links_for_address_from_collection = {
                x["account_address"]: x["token_holding"]["token_amount"]
                for x in db_to_use[Collections.tokens_links_v2].find(
                    {"token_holding.token_address": token_address_str}
                )
            }
            token_holders = token_links_for_address_from_collection
            token_holders = dict(
                sorted(
                    token_holders.items(), key=lambda item: int(item[1]), reverse=True
                )
            )
            total_event_count = len(token_holders)
            token_holder_addresses = list(token_holders.keys())
            token_holders_to_show = token_holder_addresses[skip : (skip + limit)]
            token_holders = {
                k: int(v)
                for k, v in token_holders.items()
                if k in token_holders_to_show
            }
            token_holders = sorted(
                token_holders.items(), key=operator.itemgetter(1), reverse=True
            )
        else:
            token_holders = []
            total_event_count = 0
            decimals = 0
        html = process_token_holders_to_HTML_v2(
            request,
            token_holders,
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
    grpcclient: GRPCClient = Depends(get_grpcclient),
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    tags: dict = Depends(get_labeled_accounts),
):
    limit = 20
    # token_address_str = token_address_str.replace("&lt;", "<").replace("&gt;", ">")
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    # motor_db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    metadata = None
    if api_key != request.app.env["API_KEY"]:
        return "No valid api key supplied."
    else:
        stored_tag = db_to_use[Collections.tokens_tags].find_one({"_id": tag})
        is_PTRT = tag == "PTRT"
        if not stored_tag:
            return None

        pipeline = [
            {"$match": {"contract": {"$in": stored_tag["contracts"]}}},
            {"$match": {"hidden": False}},
        ]
        result = list(
            db_to_use[Collections.tokens_token_addresses_v2].aggregate(pipeline)
        )
        if len(result) > 0:
            token_address_for_tag = MongoTypeTokenAddress(**result[0])

        metadata = find_token_address_from_contract_address(
            db_to_use, stored_tag["contracts"][0]
        )

        return templates.TemplateResponse(
            "tokens/generic/token_display_fungible.html",
            {
                "env": request.app.env,
                "request": request,
                "is_PTRT": is_PTRT,
                "net": net,
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
                    token_address_for_tag.token_id
                    if token_address_for_tag
                    else "unknown"
                ),
                "tag": tag,
                "stored_tag": stored_tag,
                "user": user,
                "tags": tags,
            },
        )


@router.get(
    "/ajax_token_ids_for_tag_multiple_use/{net}/{tag}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def ajax_token_ids_for_tag_mulitple(
    request: Request,
    net: str,
    tag: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    tags: dict = Depends(get_labeled_accounts),
):
    limit = 20
    # token_address_str = token_address_str.replace("&lt;", "<").replace("&gt;", ">")
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    # motor_db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    metadata = None
    typed_tokens_tag = None
    single_use_contract = False
    if api_key != request.app.env["API_KEY"]:
        return "No valid api key supplied."
    else:
        if requested_page > -1:
            skip = requested_page * limit
        else:
            nr_of_pages, _ = divmod(total_rows, limit)
            skip = nr_of_pages * limit

        token_addresses_for_tag = []
        stored_tag = db_to_use[Collections.tokens_tags].find_one({"_id": tag})
        is_PTRT = tag == "PTRT"
        if not stored_tag:
            return None

        tag_id_count_result = list(
            db_to_use[Collections.pre_addresses_by_contract_count].find(
                {"_id": {"$in": stored_tag["contracts"]}}
            )
        )
        tag_id_count = sum([x["count"] for x in tag_id_count_result])
        pipeline = [
            {"$match": {"contract": {"$in": stored_tag["contracts"]}}},
            {"$match": {"hidden": False}},
            {"$sort": {"last_height_processed": DESCENDING}},
            {
                "$facet": {
                    "data": [{"$skip": skip}, {"$limit": limit}],
                }
            },
        ]
        result = list(
            db_to_use[Collections.tokens_token_addresses_v2].aggregate(pipeline)
        )
        if len(result) > 0:
            token_addresses_for_tag = [
                MongoTypeTokenAddress(**x) for x in result[0]["data"]
            ]
        html = process_token_ids_for_tag_to_HTML_v2(
            request,
            token_addresses_for_tag,
            tag_id_count,
            requested_page,
            user,
            tags,
            net,
            metadata,
            tag,
            # decimals,
        )
        return html
