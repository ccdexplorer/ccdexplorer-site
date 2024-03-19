# ruff: noqa: F403, F405, E402, E501, E722, F401

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from app.classes.dressingroom import (
    MakeUp,
    TransactionClassifier,
    MakeUpRequest,
    RequestingRoute,
)
from ccdefundamentals.transaction import Transaction

# from ccdefundamentals.ccdscan import CCDScan
from ccdefundamentals.tooter import Tooter, TooterType, TooterChannel

# import requests
# import json
from ccdefundamentals.enums import NET
from ccdefundamentals.mongodb import (
    MongoDB,
    Collections,
    MongoTypePayday,
    MongoTypePaydayAPYIntermediate,
    MongoTypeModule,
)
from ccdefundamentals.GRPCClient import GRPCClient

from ccdefundamentals.GRPCClient.CCD_Types import *
from app.jinja2_helpers import *
from app.env import *
from app.state.state import *

router = APIRouter()


@router.get("/transaction/{tx_hash}", response_class=RedirectResponse)
async def redirect_transaction_to_mainnet(request: Request, tx_hash: str):
    response = RedirectResponse(url=f"/mainnet/transaction/{tx_hash}", status_code=302)
    return response


@router.get("/{net}/transaction/{tx_hash}", response_class=HTMLResponse)
async def request_transaction_mongo(
    request: Request,
    net: str,
    tx_hash: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
    contracts_with_tag_info: dict = Depends(get_contracts_with_tag_info),
    ccd_historical: dict = Depends(get_exchange_rates_ccd_historical),
    # token_addresses_with_markup: dict = Depends(get_token_addresses_with_markup),
    credential_issuers: list = Depends(get_credential_issuers),
):
    """
    Endpoint to display a transaction. This method makes 2 calls (in order) to retrieve the required information.
    First call is to the dashboard (as we currently do not have a table with all tx hashes stored). We need
    additional information on the block the transaction was finalized in, which we get by querying the node
    with the `block_hash` from the transaction.
    Attributes:
        tx_hash (str): the transaction hash.
    Returns:
        template (HTMLResponse): transaction/transaction.html

    """
    # r = requests.get(
    #     f"http://127.0.0.1:7000/v1/mainnet/transaction/{tx_hash}", verify=True
    # )
    # if r.status_code == 200:
    #     result = json.loads(r.json())
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    result = db_to_use[Collections.transactions].find_one(tx_hash)
    # possibly in the other net?
    if not result:
        if request.app.env["NET"] == "mainnet":
            result = mongodb.testnet[Collections.transactions].find_one(tx_hash)
            if result:
                # switch net
                env["NET"] = "testnet"
        else:
            result = mongodb.mainnet[Collections.transactions].find_one(tx_hash)
            if result:
                # switch net
                env["NET"] = "mainnet"
    if result:
        result = CCD_BlockItemSummary(**result)

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
                "requesting_route": RequestingRoute.transaction,
            }
        )
        classified_tx = MakeUp(makeup_request=makeup_request).prepare_for_display(
            result, "", False
        )
        tx = classified_tx.dct

        return templates.TemplateResponse(
            "transaction/transaction.html",
            {
                "request": request,
                "env": request.app.env,
                "tx_hash": tx_hash,
                "net": net,
                "transaction": tx,
                "status": "finalized",
                "block_hash": result.block_info.hash,
                "user": user,
                "tags": tags,
                "cns_domain_name": classified_tx.cns_domain.domain_name,
                "events_list": classified_tx.events_list,
                "cns_tx_message": classified_tx.cns_domain.action,
                "classified_tx": classified_tx,
            },
        )
    else:
        return "tx not found?"
