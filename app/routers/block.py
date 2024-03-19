# ruff: noqa: F403, F405, E402, E501, E722
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

##
from ccdefundamentals.enums import NET

from ccdefundamentals.mongodb import *
from ccdefundamentals.GRPCClient.CCD_Types import *


from app.ajax_helpers import (
    process_payday_account_rewards_to_HTML,
    process_payday_account_rewards_to_HTML_v2,
    process_payday_pool_rewards_to_HTML,
    process_payday_pool_rewards_to_HTML_v2,
    process_transactions_to_HTML,
    transactions_html_footer,
    mongo_pagination_html_header,
    mongo_transactions_html_header,
)
from app.classes.dressingroom import MakeUp, TransactionClassifier, MakeUpRequest

from env import *
from app.jinja2_helpers import *
from app.Recurring.recurring import Recurring
from ccdefundamentals.tooter import Tooter, TooterType, TooterChannel
from app.state.state import *
from ccdefundamentals.GRPCClient import GRPCClient


router = APIRouter()


@router.get("/block/{block_hash}", response_class=RedirectResponse)
async def redirect_block_to_mainnet(request: Request, block_hash: str):
    response = RedirectResponse(url=f"/mainnet/block/{block_hash}", status_code=302)
    return response


@router.get("/{net}/block/{block_value}", response_class=HTMLResponse)
async def request_block(
    request: Request,
    net: str,
    block_value: str,
    # block_height: Optional[str] = None,
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    recurring: Recurring = Depends(get_recurring),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
):
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    # grpcclient.switch_to_net(env["NET"])
    # tooter.send(channel=TooterChannel.NOTIFIER, message=f'{user_string(user)} visited a /block/{block_hash}.', notifier_type=TooterType.INFO)

    possible_baker = None
    error = None
    if block_value.isnumeric():  # it's a block_height
        # last_finalized_block = grpcclient.get_block_info("last_final", net=NET(net))

        try:
            block_info = grpcclient.get_finalized_block_at_height(
                int(block_value), net=NET(net)
            )
        except:
            block_info = None

        if not block_info:
            error = {
                "error": True,
                "errorMessage": f"No block on {net} found at {block_value}.",
            }
            return templates.TemplateResponse(
                "account/account_account_error.html",
                {
                    "env": request.app.env,
                    "request": request,
                    "net": net,
                    "error": error,
                },
            )
    else:
        try:
            block_info = grpcclient.get_block_info(block_value, net=NET(net))

            possible_baker = None
        except:
            error = {
                "error": True,
                "errorMessage": f"No block on {net} found at {block_value}.",
            }
            return templates.TemplateResponse(
                "account/account_account_error.html",
                {
                    "env": request.app.env,
                    "request": request,
                    "net": net,
                    "error": error,
                },
            )
    # else:
    #     user = None

    result = mongodb.mainnet[Collections.paydays].find_one({"_id": block_value})
    # if True, this block has payday rewards
    if result:
        payday = True
    else:
        payday = False

    # net_postfix = "/?net=testnet" if "net" in request.query_params else ""
    return templates.TemplateResponse(
        "block/block.html",
        {
            "request": request,
            # "net_postfix": net_postfix,
            "env": request.app.env,
            "payday": payday,
            "baker_nodes": recurring.baker_nodes_by_baker_id,
            "non_baker_nodes": recurring.non_baker_nodes_by_node_id,
            "old": False,
            "net": net,
            "block_info": block_info,
            "possible_baker": possible_baker,
            "user": user,
            "tags": tags,
        },
    )


@router.get(
    "/ajax_chain_parameters_html_v2/{net}/{block_hash}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_chain_parameters_html_v2(
    request: Request,
    net: str,
    block_hash: str,
    api_key: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tags: dict = Depends(get_labeled_accounts),
):
    """
    Add {net}.
    """
    user: UserV2 = get_user_detailsv2(request)
    if api_key != request.app.env["API_KEY"]:
        return "No valid api key supplied."
    else:
        chain_parameters = grpcclient.get_block_chain_parameters(
            block_hash, net=NET(net)
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
    "/ajax_special_events_html_v2/{net}/{block_hash}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_special_events_html_v2(
    request: Request,
    net: str,
    block_hash: str,
    api_key: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tags: dict = Depends(get_labeled_accounts),
):
    user: UserV2 = get_user_detailsv2(request)
    if api_key != request.app.env["API_KEY"]:
        return "No valid api key supplied."
    else:
        special_events = grpcclient.get_block_special_events(block_hash, net=NET(net))
        html = templates.get_template("/block/block_special_events.html").render(
            {
                "se": special_events,
                "user": user,
                "tags": tags,
                "net": net,
                "baker_nodes": recurring.baker_nodes_by_baker_id,
                "request": request,
            }
        )

        return html


@router.get(
    "/ajax_payday_account_rewards_html_v2/{block_hash}/{requested_page}/{total_rows}/{date_string}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_payday_account_rewards_html_v2(
    request: Request,
    block_hash: str,
    requested_page: int,
    total_rows: int,
    date_string: str,
    api_key: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    tags: dict = Depends(get_labeled_accounts),
):
    limit = 20
    user: UserV2 = get_user_detailsv2(request)
    if request.app.env["NET"] == "mainnet":
        if api_key != request.app.env["API_KEY"]:
            return "No valid api key supplied."
        else:
            result = mongodb.mainnet[Collections.paydays].find_one({"_id": block_hash})
            # if True, this block has payday rewards
            if result:
                # requested page = 0 indicated the first page
                # requested page = -1 indicates the last page
                if requested_page > -1:
                    skip = requested_page * limit
                else:
                    nr_of_pages, _ = divmod(total_rows, limit)
                    skip = nr_of_pages * limit

                result = list(
                    mongodb.mainnet[Collections.paydays_rewards].aggregate(
                        [
                            {"$match": {"date": date_string}},
                            {"$match": {"account_id": {"$exists": True}}},
                            {
                                "$facet": {
                                    "metadata": [{"$count": "total"}],
                                    "data": [
                                        {"$skip": int(skip)},
                                        {"$limit": int(limit)},
                                    ],
                                }
                            },
                        ]
                    )
                )[0]

                reward_result = [MongoTypeAccountReward(**x) for x in result["data"]]
                html = process_payday_account_rewards_to_HTML_v2(
                    request,
                    reward_result,
                    result["metadata"][0]["total"],
                    requested_page,
                    user,
                    tags,
                )

                return html
            else:
                return None
    else:
        return templates.TemplateResponse(
            "testnet/not-available-single.html",
            {
                "env": request.app.env,
                "request": request,
                "user": user,
            },
        )


@router.get(
    "/ajax_payday_pool_rewards_html_v2/{block_hash}/{requested_page}/{total_rows}/{date_string}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_payday_pool_rewards_html_v2(
    request: Request,
    block_hash: str,
    requested_page: int,
    total_rows: int,
    date_string: str,
    api_key: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    tags: dict = Depends(get_labeled_accounts),
):
    limit = 20
    user: UserV2 = get_user_detailsv2(request)
    if request.app.env["NET"] == "mainnet":
        if api_key != request.app.env["API_KEY"]:
            return "No valid api key supplied."
        else:
            result = mongodb.mainnet[Collections.paydays].find_one({"_id": block_hash})
            # if True, this block has payday rewards
            if result:
                # requested page = 0 indicated the first page
                # requested page = -1 indicates the last page
                if requested_page > -1:
                    skip = requested_page * limit
                else:
                    nr_of_pages, _ = divmod(total_rows, limit)
                    skip = nr_of_pages * limit

                result = list(
                    mongodb.mainnet[Collections.paydays_rewards].aggregate(
                        [
                            {"$match": {"date": date_string}},
                            {"$match": {"pool_owner": {"$exists": True}}},
                            {
                                "$facet": {
                                    "metadata": [{"$count": "total"}],
                                    "data": [
                                        {"$skip": int(skip)},
                                        {"$limit": int(limit)},
                                    ],
                                }
                            },
                        ]
                    )
                )[0]

                reward_result = [MongoTypePoolReward(**x) for x in result["data"]]
                html = process_payday_pool_rewards_to_HTML_v2(
                    request,
                    reward_result,
                    result["metadata"][0]["total"],
                    requested_page,
                    user,
                    tags,
                )

                return html
            else:
                return None
    else:
        return templates.TemplateResponse(
            "testnet/not-available-single.html",
            {
                "env": request.app.env,
                "request": request,
                "user": user,
            },
        )


@router.get(
    "/ajax_block_transactions_html_v2/{net}/{block_hash}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def ajax_block_transactions_html(
    request: Request,
    net: str,
    block_hash: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    mongodb: MongoDB = Depends(get_mongo_db),
    contracts_with_tag_info: dict = Depends(get_contracts_with_tag_info),
    ccd_historical: dict = Depends(get_exchange_rates_ccd_historical),
    tags: dict = Depends(get_labeled_accounts),
    # token_addresses_with_markup: dict = Depends(get_token_addresses_with_markup),
    credential_issuers: list = Depends(get_credential_issuers),
):
    limit = 20
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet

    if api_key != request.app.env["API_KEY"]:
        return "No valid api key supplied."
    else:
        tx_tabs: dict[TransactionClassifier, list] = {}
        tx_tabs_active: dict[TransactionClassifier, bool] = {}

        for tab in TransactionClassifier:
            tx_tabs[tab] = []

        try:
            block_info = CCD_BlockInfo(
                **db_to_use[Collections.blocks].find_one(block_hash)
            )
        except:
            block_info = None
        if not block_info:
            return ""
        else:
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

            tx_result = [
                CCD_BlockItemSummary(**x)
                for x in db_to_use[Collections.transactions]
                .find({"_id": {"$in": block_info.transaction_hashes}})
                .skip(skip)
                .limit(limit)
            ]

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
                block_info.transaction_count,
                requested_page,
                tx_tabs,
                tx_tabs_active,
                block_transactions=True,
            )

            for tab in TransactionClassifier:
                html += process_transactions_to_HTML(
                    tx_tabs[tab], tab.value, tx_tabs_active[tab], tags
                )

            html += transactions_html_footer()
            return html
