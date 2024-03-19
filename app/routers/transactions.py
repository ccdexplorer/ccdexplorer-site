from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from app.classes.dressingroom import MakeUp, TransactionClassifier, MakeUpRequest
from ccdefundamentals.transaction import Transaction
from app.utils import user_string
from app.ajax_helpers import (
    transactions_html_footer,
    mongo_transactions_html_header,
    process_transactions_to_HTML,
)
from app.jinja2_helpers import *
from app.env import *
from typing import Union
from app.state.state import *
import datetime as dt
from ccdefundamentals.tooter import Tooter, TooterType, TooterChannel
from ccdefundamentals.mongodb import (
    MongoDB,
    Collections,
    MongoTypeBlockPerDay,
    MongoMotor,
)
from ccdefundamentals.GRPCClient import GRPCClient


# from ccdefundamentals.transaction import Transaction
from ccdefundamentals.GRPCClient.CCD_Types import *

from app.Recurring.recurring import Recurring

# import math
from rich import print

router = APIRouter()


@router.get("/{net}/transactions-search", response_class=HTMLResponse)
async def request_block_node(
    request: Request,
    net: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    user: UserV2 = get_user_detailsv2(request)
    tooter.send(
        channel=TooterChannel.NOTIFIER,
        message=f"{user_string(user)} visited /transactions-search.",
        notifier_type=TooterType.INFO,
    )

    return templates.TemplateResponse(
        "transactions_search/start.html",
        {"request": request, "env": request.app.env, "user": user, "net": net},
    )


@router.get(
    "/ajax_transactions_search/{net}/{transfer_type}/{gte}/{lte}/{start_date}/{end_date}/{current_page}/{sort_on}/{sort_direction}/{all}/{memo_only}/{scheduled}/{memo_contains}",
    response_class=HTMLResponse,
)
async def request_transactions_mongodb(
    request: Request,
    net: str,
    transfer_type: str,
    gte: str,
    lte: str,
    start_date: str,
    end_date: str,
    current_page: str,
    sort_on: str,
    sort_direction: int,
    all: str,
    memo_only: str,
    scheduled: str,
    memo_contains: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
    transfer_memos: dict = Depends(get_memo_transfers),
    contracts_with_tag_info: dict = Depends(get_contracts_with_tag_info),
    ccd_historical: dict = Depends(get_exchange_rates_ccd_historical),
    # token_addresses_with_markup: dict = Depends(get_token_addresses_with_markup),
    credential_issuers: list = Depends(get_credential_issuers),
    blocks_per_day: dict[str, MongoTypeBlockPerDay] = Depends(get_blocks_per_day),
):
    """
    Endpoint to search for transactions given parameters.
    Parameter `all` refers to regular transfers.
    Attributes:

    Returns:

    """
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet

    if memo_contains != "<empty string>":
        tooter.send(
            channel=TooterChannel.NOTIFIER,
            message=f'{user_string(user)} searched for "{memo_contains}".',
            notifier_type=TooterType.INFO,
        )

        filter_on_tx_hashes = True
        keys_with_sub_string = []
        memo_contains_lower = memo_contains.lower()
        for x in transfer_memos.keys():
            memo = x
            try:
                if memo_contains_lower in memo:
                    keys_with_sub_string.append(memo)
            except Exception as e:
                print(e)
                pass

        hashes_with_sub_string = [transfer_memos[x] for x in keys_with_sub_string]

        list_of_tx_hashes_with_memo_predicate = [
            item for sublist in hashes_with_sub_string for item in sublist
        ]
    else:
        list_of_tx_hashes_with_memo_predicate = []
        filter_on_tx_hashes = False

    # this is the case if we are paginating a page forward or backward
    if current_page.isnumeric():
        current_page = int(current_page)
        limit = 20
        skip = current_page * limit
    # this is the case if we do start or end
    else:
        # only for last do we have `:`, as we need to supply the remaining nr of txs to show.
        if ":" in current_page:
            [_, current_page] = current_page.split(":")[1].split("-")

            current_page = int(current_page)
            limit = 20
            skip = current_page * limit
        else:
            # we are requesting the first page
            current_page = 0
            limit = 20
            skip = current_page * limit

    try:
        gte = int(gte.replace(",", "").replace(".", ""))
        lte = int(lte.replace(",", "").replace(".", ""))

        if lte == 0:
            lte = 100_000
        start_date_dt = dateutil.parser.parse(start_date).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_date_dt = dateutil.parser.parse(end_date).replace(
            hour=23, minute=59, second=59, microsecond=999
        )
        amended_start_date = (
            f"{(dateutil.parser.parse(start_date)-dt.timedelta(days=1)):%Y-%m-%d}"
        )
        # start_block = recurring.blocks_at_end_of_day.get(
        #     amended_start_date, {"blockHeight": 0}
        # )["blockHeight"]
        # start_block = max(start_block - 6840, 0)
        # end_block = recurring.blocks_at_end_of_day.get(
        #     end_date, {"blockHeight": 1_000_000_000}
        # )["blockHeight"]
        # start_block = blocks_per_day.get(amended_start_date)

        start_block = blocks_per_day.get(amended_start_date)
        if start_block:
            start_block = start_block.height_for_first_block
        else:
            start_block = 0

        # start_block = max(start_block - 6840, 0)

        # end_block = recurring.blocks_at_end_of_day.get(
        #     end_date, {"blockHeight": 1_000_000_000}
        # )["blockHeight"]

        end_block = blocks_per_day.get(end_date)
        if end_block:
            end_block = end_block.height_for_last_block
        else:
            end_block = 1_000_000_000
    except:
        error = True

    all = False if all == "false" else True
    memo_only = False if memo_only == "false" else True
    scheduled = False if scheduled == "false" else True

    if all:
        transfer_type = "account_transfer"
        filter_on_tx_hashes = False
    elif scheduled:
        transfer_type = "transferred_with_schedule"
        filter_on_tx_hashes = False
    else:
        transfer_type = "account_transfer"

    if all:
        txs_hashes = []
    else:
        pipeline = mongodb.search_transfers_based_on_indices_v2(
            transfer_type,
            gte,
            lte,
            start_block,
            end_block,
            list_of_tx_hashes_with_memo_predicate,
            filter_on_tx_hashes,
        )
        result_txs_for_account = (
            await mongomotor.mainnet[Collections.involved_accounts_transfer]
            .aggregate(pipeline)
            .to_list(20)
        )
        txs_hashes = [x["_id"] for x in result_txs_for_account]

    # now apply hashes to collection transactions to filter

    pipeline = mongodb.search_transfers_mongo_v2(
        transfer_type,
        gte,
        lte,
        start_date_dt,
        end_date_dt,
        skip,
        limit,
        txs_hashes,
        sort_on,
        sort_direction,
        filter_on_tx_hashes,
    )
    result = list(db_to_use[Collections.transactions].aggregate(pipeline))

    txs = [CCD_BlockItemSummary(**x) for x in result[0]["data"]]
    if "total" in result[0]:
        len_search_result = result[0]["total"]
    else:
        len_search_result = 0

    tx_tabs: dict[TransactionClassifier, list] = {}
    tx_tabs_active: dict[TransactionClassifier, bool] = {}

    for tab in TransactionClassifier:
        tx_tabs[tab] = []

    for transaction in txs:
        makeup_request = MakeUpRequest(
            **{
                "net": net,
                "grpcclient": grpcclient,
                "mongodb": mongodb,
                "tags": tags,
                "user": user,
                "contracts_with_tag_info": contracts_with_tag_info,
                "ccd_historical": ccd_historical,
                # "token_addresses_with_markup": token_addresses_with_markup,
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
        None, len_search_result, current_page, tx_tabs, tx_tabs_active
    )

    for tab in TransactionClassifier:
        html += process_transactions_to_HTML(
            tx_tabs[tab], tab.value, tx_tabs_active[tab], tags
        )

    html += transactions_html_footer()
    return html
