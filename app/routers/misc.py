# ruff: noqa: F403, F405, E402, E501, E722, F401

from fastapi import APIRouter, Request, Depends
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
    JSONResponse,
    FileResponse,
    Response,
)

from typing import Optional, Union

# from app.__chain import Chain
from typing import Optional
from pymongo import ASCENDING, DESCENDING
import random
from app.classes.dressingroom import MakeUp, TransactionClassifier, MakeUpRequest
from app.jinja2_helpers import *
from app.env import *
from app.state.state import *
from app.Recurring.recurring import Recurring
from datetime import timedelta
from ccdexplorer_fundamentals.cns import CNSDomain

from ccdexplorer_fundamentals.mongodb import MongoDB, Collections, MongoMotor
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import *
from ccdexplorer_fundamentals.GRPCClient import GRPCClient

import requests
from app.ajax_helpers import (
    process_transactions_to_HTML,
    transactions_html_footer,
    mongo_transactions_html_header,
)
from ccdexplorer_fundamentals.tooter import Tooter, TooterType, TooterChannel

router = APIRouter()


@router.get("/grant-proposal")
async def grant_proposal(
    request: Request,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    token = request.cookies.get("access-token")
    user: UserV2 = get_user_detailsv2(request)
    tooter.send(
        channel=TooterChannel.NOTIFIER,
        message=f"(Site): Grant proposal requested!",
        notifier_type=TooterType.INFO,
    )
    return FileResponse("persist/grant-proposal-dec-2022.pdf")


@router.get("/", response_class=RedirectResponse)
async def home(
    request: Request,
    tags: dict = Depends(get_labeled_accounts),
):
    response = RedirectResponse(url="/mainnet", status_code=302)
    return response


@router.get("/mainnet", response_class=HTMLResponse)
async def redirect_to_mainnet(
    request: Request,
    tags: dict = Depends(get_labeled_accounts),
):
    user: UserV2 = get_user_detailsv2(request)
    net = "mainnet"
    return templates.TemplateResponse(
        "home.html",
        {"env": request.app.env, "request": request, "user": user, "net": net},
    )


@router.get("/testnet", response_class=HTMLResponse)
async def redirect_to_testnet(
    request: Request,
    tags: dict = Depends(get_labeled_accounts),
):
    user: UserV2 = get_user_detailsv2(request)
    net = "testnet"
    return templates.TemplateResponse(
        "home.html",
        {"env": request.app.env, "request": request, "user": user, "net": net},
    )


@router.get("/{net}/insights/labeled-accounts", response_class=HTMLResponse)
async def labeled_accounts(
    request: Request,
    net: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
    # nightly_accounts: dict = Depends(get_nightly_accounts)
):
    user: UserV2 = get_user_detailsv2(request)
    if net == "mainnet":
        return templates.TemplateResponse(
            "labeled-accounts.html",
            {
                "env": request.app.env,
                "request": request,
                "user": user,
                "tags": tags,
                "net": net,
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
    f"/delegate-to-72723-for-free-access",
    response_class=RedirectResponse,
)
async def redirect_delegator():
    response = RedirectResponse(
        url="/settings/user/subscription/plans", status_code=302
    )
    return response


@router.get("/{net}/recent/actions", response_class=HTMLResponse)
async def recent_actions(
    request: Request,
    net: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
):
    user: UserV2 = get_user_detailsv2(request)
    return templates.TemplateResponse(
        "actions/actions.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "tags": tags,
            "net": net,
        },
    )


@router.get("/api", response_class=HTMLResponse)
async def api(
    request: Request,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    exchange_rates: dict = Depends(get_exchange_rates),
):
    user: UserV2 = get_user_detailsv2(request)
    return templates.TemplateResponse(
        "api-docs.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "exchange_rates": exchange_rates,
            "net": "mainnet",
        },
    )


@router.get("/mainnet/exchange-rates", response_class=HTMLResponse)
async def exchange_rates(
    request: Request,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    exchange_rates: dict = Depends(get_exchange_rates),
):
    user: UserV2 = get_user_detailsv2(request)
    return templates.TemplateResponse(
        "exchange_rates.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "exchange_rates": exchange_rates,
            "net": "mainnet",
        },
    )


@router.get(
    "/ajax_protocol_updates/mainnet/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def ajax_protocol_updates(
    request: Request,
    requested_page: int,
    total_rows: int,
    api_key: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
    exchange_rates: dict = Depends(get_exchange_rates),
    contracts_with_tag_info: dict = Depends(get_contracts_with_tag_info),
    ccd_historical: dict = Depends(get_exchange_rates_ccd_historical),
    # token_addresses_with_markup: dict = Depends(get_token_addresses_with_markup),
    credential_issuers: list = Depends(get_credential_issuers),
):
    user: UserV2 = get_user_detailsv2(request)
    limit = 500

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
        # special case if total_rows equals a limt multiple
        if skip == total_rows:
            skip = (nr_of_pages - 1) * limit

    pipeline = [
        {"$sort": {"block_info.height": DESCENDING}},
        {"$match": {"update": {"$exists": True}}},
        {"$match": {"update.payload.micro_ccd_per_euro_update": {"$exists": False}}},
    ]
    result = (
        await mongomotor.mainnet[Collections.transactions]
        .aggregate(pipeline)
        .to_list(1_000_000)
    )
    protocol_updates = [CCD_BlockItemSummary(**x) for x in result]
    protocol_updates.sort(key=lambda x: x.block_info.height, reverse=True)

    for transaction in protocol_updates:
        makeup_request = MakeUpRequest(
            **{
                "net": "mainnet",
                "grpcclient": grpcclient,
                "mongodb": mongodb,
                "tags": tags,
                "user": user,
                "contracts_with_tag_info": contracts_with_tag_info,
                "ccd_historical": ccd_historical,
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
        None, len(protocol_updates), 0, tx_tabs, tx_tabs_active
    )

    for tab in TransactionClassifier:
        html += process_transactions_to_HTML(
            tx_tabs[tab], tab.value, tx_tabs_active[tab], tags
        )
    return html


@router.get("/mainnet/chain-information", response_class=HTMLResponse)
async def chain_information(
    request: Request,
    # recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
    exchange_rates: dict = Depends(get_exchange_rates),
    contracts_with_tag_info: dict = Depends(get_contracts_with_tag_info),
    ccd_historical: dict = Depends(get_exchange_rates_ccd_historical),
    # token_addresses_with_markup: dict = Depends(get_token_addresses_with_markup),
    credential_issuers: list = Depends(get_credential_issuers),
):
    user: UserV2 = get_user_detailsv2(request)

    ip = grpcclient.get_identity_providers("last_final")
    ar = grpcclient.get_anonymity_revokers("last_final")

    return templates.TemplateResponse(
        "chain-information/chain_information.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "ar": ar,
            "ip": ip,
            "net": "mainnet",
        },
    )


@router.get("/mainnet/not-found/{value}", response_class=HTMLResponse)
async def not_found(
    request: Request,
    value: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    user: UserV2 = get_user_detailsv2(request)
    return templates.TemplateResponse(
        "not-found.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "value": value,
            "net": "mainnet",
        },
    )


@router.get(
    "/ajax_recent_actions/{net}/{action_type}/{days}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def ajax_recent_actions(
    request: Request,
    net: str,
    action_type: str,
    days: int,
    requested_page: int,
    total_rows: int,
    api_key: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    contracts_with_tag_info: dict = Depends(get_contracts_with_tag_info),
    ccd_historical: dict = Depends(get_exchange_rates_ccd_historical),
    tags: dict = Depends(get_labeled_accounts),
    # token_addresses_with_markup: dict = Depends(get_token_addresses_with_markup),
    credential_issuers: list = Depends(get_credential_issuers),
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

        if action_type != "account_creation":
            action_query = {
                "$match": {
                    f"account_transaction.effects.{action_type}": {"$exists": True}
                }
            }
        else:
            action_query = {"$match": {f"{action_type}": {"$exists": True}}}

        pipeline = [
            action_query,
            {"$match": {"block_info.slot_time": {"$gte": cutoff}}},
            {"$sort": {"block_info.slot_time": DESCENDING}},
            {
                "$facet": {
                    "metadata": [{"$count": "total"}],
                    "data": [{"$skip": int(skip)}, {"$limit": int(limit)}],
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
            await db_to_use[Collections.transactions]
            .aggregate(pipeline)
            .to_list(100_000)
        )
        tx_result = [CCD_BlockItemSummary(**x) for x in dd[0]["data"]]
        total_row_count = dd[0]["total"]

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
                        # "token_addresses_with_markup": token_addresses_with_markup,
                        "credential_issuers": credential_issuers,
                        "app": request.app,
                    }
                )
                classified_tx = MakeUp(
                    makeup_request=makeup_request
                ).prepare_for_display(transaction, "", False)

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
            word=f"{action_type}_action",
        )

        for tab in TransactionClassifier:
            html += process_transactions_to_HTML(
                tx_tabs[tab], tab.value, tx_tabs_active[tab], tags
            )

        html += transactions_html_footer()
        return html


def get_web23_domain_name(mongodb: MongoDB, domain_name):
    ccd_token_tags = mongodb.mainnet[Collections.tokens_tags].find_one({"_id": ".ccd"})

    if ccd_token_tags:
        contracts_in_ccd_token_tag = MongoTypeTokensTag(**ccd_token_tags).contracts
        query = {"contract": {"$in": contracts_in_ccd_token_tag}}

        domain_names_tokens = [
            MongoTypeTokenAddress(**x)
            for x in mongodb.mainnet[Collections.tokens_token_addresses_v2].find(query)
        ]
    else:
        domain_names_tokens = []
    possible_token = [
        x for x in domain_names_tokens if x.token_metadata.name == domain_name
    ]
    if len(possible_token) > 0:
        result = mongodb.mainnet[Collections.tokens_links_v2].find_one(
            {"token_holding.token_address": possible_token[0].id}
        )
        if result:
            return result["account_address"]
        else:
            return None
    else:
        return None

    # domain_names_dict = {}
    # for x in domain_names_tokens:
    #     if x.token_metadata:
    #         if x.token_metadata.name:
    #             owner_address = list(x.token_holders.keys())[0]
    #             domain_names_dict[x.token_metadata.name] = list(x.token_holders.keys())[
    #                 0
    #             ]
    # return domain_names_dict.get(domain_name, None)


@router.get("/{net}/go/{value}", response_class=RedirectResponse)
async def go(
    request: Request,
    net: str,
    value: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    """
    The method called when searching in the search field.
    Order of operations:
    1. Check if value is numeric. Either an account_index/baker_id/block_height.
    2. For each value it's first tried on current net. If that fails, we try
    the other net.
    """
    user: UserV2 = get_user_detailsv2(request)
    # net = "mainnet"
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet

    if value.isnumeric():  # account_index/baker_id/block_height
        account_info = None
        try:
            account_info = grpcclient.get_account_info(
                block_hash="last_final", account_index=int(value), net=NET(net)
            )
        except:
            # possibly on wrong net?
            if net == "mainnet":
                net = "testnet"
                try:
                    account_info = grpcclient.get_account_info(
                        block_hash="last_final",
                        account_index=int(value),
                        net=NET(net),
                    )
                except:
                    # switch back in case of failure
                    net = "mainnet"

            else:
                net = "mainnet"
                try:
                    account_info = grpcclient.get_account_info(
                        block_hash="last_final",
                        account_index=int(value),
                        net=NET(net),
                    )
                except:
                    # switch back in case of failure
                    net = "testnet"

        if account_info:
            return f"/{net}/account/{account_info.address}"
        else:
            try:
                block_hash = grpcclient.get_finalized_block_at_height(
                    int(value), net=NET(net)
                ).hash
                return f"/{net}/block/{block_hash}?block_height={value}"
            except:
                return f"/mainnet/not-found/{value}"

        # AESIRX
    if value[0] == "@":
        result = mongodb.mainnet[Collections.tokens_token_addresses_v2].find_one(
            {"token_metadata.name": value}
        )
        # if not result:
        #     result = mongodb.mainnet[Collections.tokens_token_addresses_v2].find_one(
        #         {"token_metadata.name": value}
        #     )

        if result:
            result = MongoTypeTokenAddress(**result)
            if len(list(result.token_holders.keys())) > 0:
                token_holder = list(result.token_holders.keys())[0]
                return f"/{net}/account/{token_holder}"
            else:
                return f"/mainnet/not-found/{value}"

    if len(value) <= 50:
        result = mongodb.mainnet[Collections.nightly_accounts].find_one(
            {"_id": {"$regex": f"{value}"}}
        )
        if result:
            return f"/{net}/account/{value}"
        else:
            if len(value) == 50:
                try:
                    account_info = grpcclient.get_account_info(
                        block_hash="last_final",
                        hex_address=value,
                        net=NET(net),
                    )
                except:
                    account_info = None
                if account_info:
                    return f"/{net}/account/{account_info.address}"
                else:
                    return f"/mainnet/not-found/{value}"
            else:
                # Get possible domain name
                resolver_address = None
                net = "mainnet"
                owner_address = get_web23_domain_name(mongodb, value.lower())
                if owner_address:
                    if len(owner_address) == 50:
                        return f"/{net}/account/{owner_address}"
                    else:
                        return f"/{net}/instance/{owner_address[0]}/{owner_address[1]}"
                else:
                    return f"/mainnet/not-found/{value}"

    elif len(value) == 64:  # block or module
        result = db_to_use[Collections.modules].find_one(value)
        if result:
            return f"/{net}/module/{value}"

        result = db_to_use[Collections.transactions].find_one(value)
        if not result:
            if net == "mainnet":
                result = mongodb.testnet[Collections.transactions].find_one(value)
                if result:
                    # switch net
                    net = "testnet"
            else:
                result = mongodb.mainnet[Collections.transactions].find_one(value)
                if result:
                    # switch net
                    net = "mainnet"
        if result:
            return f"/{net}/transaction/{value}"

        result = db_to_use[Collections.blocks].find_one(value)
        if not result:
            if net == "mainnet":
                net = "testnet"
                result = grpcclient.get_block_info(value, net=NET(net))

            else:
                net = "mainnet"
                # grpcclient.switch_to_net(env["NET"])
                result = grpcclient.get_block_info(value, net=NET(net))
        if result:
            return f"/{net}/block/{value}"
    elif len(value) == 16:  # nodeId
        result = db_to_use[Collections.dashboard_nodes].find_one(value)
        if not result:
            if net == "mainnet":
                result = mongodb.testnet[Collections.dashboard_nodes].find_one(value)
                if result:
                    # switch net
                    net = "testnet"
            else:
                result = mongodb.mainnet[Collections.dashboard_nodes].find_one(value)
                if result:
                    # switch net
                    net = "mainnet"
        if result:
            return f"/{net}/node/{value}"

    # else:


@router.get("/ping")  # type:ignore
async def ping(request: Request):
    return JSONResponse(content={"success": True})


@router.get("/ajax_txs_table", response_class=HTMLResponse)
async def ajax_txs_table(
    request: Request,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    state_response = mongodb.mainnet_db["pre_render"].find_one({"_id": "tps_table"})

    return templates.TemplateResponse(
        "txs_table_htmx.html",
        {"env": request.app.env, "request": request, "s": state_response},
    )


@router.get("/{given_net}/ajax_stream_table", response_class=HTMLResponse)
async def ajax_stream_table(
    request: Request,
    given_net: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):

    for net in NET:

        try:
            block_info = grpcclient.get_block_info("last_final", net=NET(net))
            response = request.app.last_block_response[net]
            if block_info.height != request.app.last_seen_finalized_height[net]:
                response = {
                    "block_info": block_info,
                    "tokenomics_info": grpcclient.get_tokenomics_info(
                        "last_final", net=NET(net)
                    ),
                    "consensus_info": grpcclient.get_consensus_info(net=NET(net)),
                }

                request.app.last_seen_finalized_height[net] = block_info.height
                request.app.last_block_response[net] = response
        except:
            pass

    return templates.TemplateResponse(
        "stream_table_htmx.html",
        {
            "env": request.app.env,
            "net": given_net,
            "request": request,
            "s": request.app.last_block_response[NET(given_net)],
        },
    )


@router.get("/ajax_last_table", response_class=HTMLResponse)
async def ajax_last_table(
    request: Request,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tags: dict = Depends(get_labeled_accounts),
    tooter: Tooter = Depends(get_tooter),
):
    user: UserV2 = get_user_detailsv2(request)
    state_response = mongodb.mainnet_db["pre_render"].find_one(
        {"_id": "accounts_table"}
    )
    usecase_ids = get_usecases(mongodb)
    accounts_response = mongodb.mainnet_db["pre_render"].find_one(
        {"_id": "accounts_table"}
    )

    for key, response in accounts_response.items():
        if "largest" in key:
            if "amount" in key:
                response = f'<span class="small ccd">Ͼ{response["amount"]:,.2f} M</span> ({tx_hash_link(response["tx_hash"], "mainnet", schedule=True, icon_only=True)})'
            else:
                response = account_link(
                    response,
                    "mainnet",
                    from_=False,
                    nothing_=True,
                    user=None,
                    tags=tags,
                    app=request.app,
                )
        if "active" in key:
            if "tx" not in key:
                if len(response) == 50:
                    response = account_link(
                        response,
                        "mainnet",
                        from_=False,
                        nothing_=True,
                        user=None,
                        tags=tags,
                        app=request.app,
                    )
                else:
                    response = f'<a class="small" href="/usecase/{usecase_ids[response]}">🎯{response}</a>'
        accounts_response[key] = response

    return templates.TemplateResponse(
        "accounts_table_htmx.html",
        {"env": request.app.env, "request": request, "s": accounts_response},
    )


@router.get("/donate", response_class=HTMLResponse)
async def donate(
    request: Request,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    token = request.cookies.get("access-token")
    user: UserV2 = get_user_detailsv2(request)
    # tooter.send(channel=TooterChannel.NOTIFIER, message=f'{user_string(user)} visited /donate.', notifier_type=TooterType.INFO)
    return templates.TemplateResponse(
        "qr.html", {"env": request.app.env, "request": request}
    )


# can we remove this?
# sure?
@router.get("/mm", response_class=HTMLResponse)
async def memory(
    request: Request,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    tooter: Tooter = Depends(get_tooter),
):
    # Only import Pympler when we need it. We don't want it to
    # affect our process if we never call memory_summary.
    print("********************Entering mm")
    rows, timestamp = memory_profiler()
    return templates.TemplateResponse(
        "mm.html",
        {
            "env": request.app.env,
            "rows": rows,
            "timestamp": timestamp,
            "request": request,
        },
    )


@router.get("/release-notes", response_class=HTMLResponse)
async def release_notes(
    request: Request,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    tooter: Tooter = Depends(get_tooter),
):
    release_notes = reversed(
        list(mongodb.utilities[CollectionsUtilities.release_notes].find({}))
    )
    return templates.TemplateResponse(
        "release_notes.html",
        {"env": request.app.env, "request": request, "release_notes": release_notes},
    )
