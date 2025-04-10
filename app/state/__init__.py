from fastapi import Request
import httpx
from ccdexplorer_fundamentals.user_v2 import UserV2
from ccdexplorer_fundamentals.mongodb import (
    Collections,
    CollectionsUtilities,
    MongoTypeBlockPerDay,
    MongoTypePayday,
)
from ccdexplorer_fundamentals.cis import MongoTypeTokensTag, MongoTypeTokenAddress
from ccdexplorer_fundamentals.enums import NET

import datetime as dt


# async def get_ccdscan(req: Request):
#     return req.app.ccdscan


async def get_recurring(req: Request):
    return req.app.recurring


async def get_tooter(req: Request):
    return req.app.tooter


async def get_user(req: Request):
    return req.app.user


def get_paydays_per_day(
    req: Request,
):
    if (
        (
            dt.datetime.now().astimezone(dt.timezone.utc)
            - req.app.paydays_per_day_last_requested
        ).total_seconds()
        < 60
    ) and (req.app.paydays_last_blocks_validated):
        pass

    else:
        if "net" in req.path_params:
            db_to_use = (
                req.app.mongodb.testnet
                if req.path_params["net"] == "testnet"
                else req.app.mongodb.mainnet
            )
            req.app.paydays_per_day = None
            req.app.paydays_last_blocks_validated = None
        else:
            db_to_use = req.app.mongodb.mainnet

        pp = [{"$sort": {"date": -1}}, {"$limit": 1}]

        result = list(
            MongoTypePayday(**x) for x in db_to_use[Collections.paydays].aggregate(pp)
        )[0]

        req.app.paydays_last_blocks_validated = (
            result.height_for_last_block - result.height_for_first_block + 1
        )
        req.app.paydays_per_day_last_requested = dt.datetime.now().astimezone(
            dt.timezone.utc
        )

    return req.app.paydays_last_blocks_validated


def get_blocks_per_day(
    req: Request,
):
    if (
        (
            dt.datetime.now().astimezone(dt.timezone.utc)
            - req.app.blocks_per_day_last_requested
        ).total_seconds()
        < 60
    ) and (req.app.blocks_per_day):
        pass

    else:
        if "net" in req.path_params:
            db_to_use = (
                req.app.mongodb.testnet
                if req.path_params["net"] == "testnet"
                else req.app.mongodb.mainnet
            )
        else:
            db_to_use = req.app.mongodb.mainnet

        result = {
            x["_id"]: MongoTypeBlockPerDay(**x)
            for x in db_to_use[Collections.blocks_per_day].find({})
        }
        req.app.blocks_per_day = result
        req.app.blocks_per_day_last_requested = dt.datetime.now().astimezone(
            dt.timezone.utc
        )

    return req.app.blocks_per_day


async def get_nightly_accounts(app):
    if (
        (
            dt.datetime.now().astimezone(dt.timezone.utc)
            - app.nightly_accounts_last_requested
        ).total_seconds()
        < 60
    ) and (app.nightly_accounts_by_account_id):
        pass
    else:
        result = app.mongodb.mainnet[Collections.nightly_accounts].find({})
        app.nightly_accounts_by_account_id = {x["_id"][:29]: x for x in list(result)}
        # req.app.nightly_accounts_by_account_index = {x["index"]: x for x in list(result)}
        app.nightly_accounts_last_requested = dt.datetime.now().astimezone(
            dt.timezone.utc
        )

    return app.nightly_accounts_by_account_id


async def get_exchange_rates(
    req: Request,
):
    if (
        (
            dt.datetime.now().astimezone(dt.timezone.utc)
            - req.app.exchange_rates_last_requested
        ).total_seconds()
        < 10
    ) and (req.app.exchange_rates):
        pass
        # print("exchange_rates from cache.")
    else:
        response = await req.app.httpx_client.get(
            f"{req.app.api_url}/v2/mainnet/misc/exchange-rates"
        )
        response.raise_for_status()
        coll = response.json()

        req.app.exchange_rates = coll

        req.app.exchange_rates_last_requested = dt.datetime.now().astimezone(
            dt.timezone.utc
        )

    return req.app.exchange_rates


def get_exchange_rates_ccd_historical(
    req: Request,
):
    if (
        (
            dt.datetime.now().astimezone(dt.timezone.utc)
            - req.app.exchange_rates_ccd_historical_last_requested
        ).total_seconds()
        < 60
    ) and (req.app.exchange_rates_ccd_historical):
        pass

    else:
        coll = req.app.mongodb.utilities[CollectionsUtilities.exchange_rates_historical]
        req.app.exchange_rates_ccd_historical = {
            x["date"]: x["rate"] for x in coll.find({"token": "CCD"})
        }

        req.app.exchange_rates_ccd_historical_last_requested = (
            dt.datetime.now().astimezone(dt.timezone.utc)
        )

    return req.app.exchange_rates_ccd_historical


def get_historical_rates(
    req: Request,
):
    if (
        (
            dt.datetime.now().astimezone(dt.timezone.utc)
            - req.app.exchange_rates_historical_last_requested
        ).total_seconds()
        < 60 * 5
    ) and (req.app.exchange_rates_historical):
        pass

    else:
        exchange_rates_by_currency = dict({})
        result = req.app.mongodb.utilities_db["exchange_rates_historical"].find({})

        for x in result:
            if not exchange_rates_by_currency.get(x["token"]):
                exchange_rates_by_currency[x["token"]] = {}
                exchange_rates_by_currency[x["token"]][x["date"]] = x["rate"]
            else:
                exchange_rates_by_currency[x["token"]][x["date"]] = x["rate"]

        req.app.exchange_rates_historical = exchange_rates_by_currency
        req.app.exchange_rates_historical_last_requested = dt.datetime.now().astimezone(
            dt.timezone.utc
        )
    return req.app.exchange_rates_historical


def get_and_save_user_from_collection(req: Request):
    if (
        dt.datetime.now().astimezone(dt.timezone.utc) - req.app.users_last_requested
    ).total_seconds() > 5:

        result = req.app.mongodb.utilities[CollectionsUtilities.users_v2_prod].find({})
        req.app.users_from_collection = {x["token"]: UserV2(**x) for x in list(result)}
        req.app.users_last_requested = dt.datetime.now().astimezone(dt.timezone.utc)


async def get_user_detailsv2(req: Request, token: str = None):
    if not token:
        token = req.cookies.get("access-token")
    if token:
        try:
            response = await req.app.httpx_client.get(
                f"{req.app.api_url}/v2/site_user/{token}"
            )
            response.raise_for_status()
            user = response.json()
        except httpx.HTTPError:
            user = None
    else:
        user = None

    if user:
        if type(user) is not UserV2:
            user = UserV2(**user)
    return user


async def get_credential_issuers(
    req: Request,
):
    if (
        (
            dt.datetime.now().astimezone(dt.timezone.utc)
            - req.app.credential_issuers_last_requested
        ).total_seconds()
        < 9
    ) and (req.app.credential_issuers):
        credential_issuers = req.app.credential_issuers
        # print("credential_issuers from cache.")
    else:
        try:
            response = await req.app.httpx_client.get(
                f"{req.app.api_url}/v2/mainnet/misc/credential-issuers"
            )
            response.raise_for_status()
            credential_issuers = response.json()
            req.app.credential_issuers_last_requested = dt.datetime.now().astimezone(
                dt.timezone.utc
            )

        except httpx.HTTPError:
            credential_issuers = None
        req.app.credential_issuers = credential_issuers

    return credential_issuers


async def get_httpx_client(req: Request):
    return req.app.httpx_client


async def get_original_labeled_accounts(
    req: Request,
):
    if (
        (
            dt.datetime.now().astimezone(dt.timezone.utc)
            - req.app.labeled_accounts_last_requested
        ).total_seconds()
        < 9
    ) and (req.app.tags):
        tags: dict[str, MongoTypeTokensTag] = req.app.tags
        # print("labeled_accounts from cache.")
    else:
        try:
            response = await req.app.httpx_client.get(
                f"{req.app.api_url}/v2/mainnet/misc/labeled-accounts"
            )
            response.raise_for_status()
            tags = response.json()
            req.app.labeled_accounts_last_requested = dt.datetime.now().astimezone(
                dt.timezone.utc
            )
        except httpx.HTTPError:
            req.app.tags = None
            tags = None

        return tags


async def get_labeled_accounts(
    req: Request,
):
    if (
        (
            dt.datetime.now().astimezone(dt.timezone.utc)
            - req.app.labeled_accounts_last_requested
        ).total_seconds()
        < 9
    ) and (req.app.tags):
        tags: dict[str, MongoTypeTokensTag] = req.app.tags
        # print("labeled_accounts from cache.")
    else:
        try:
            response = await req.app.httpx_client.get(
                f"{req.app.api_url}/v2/mainnet/misc/community-labeled-accounts"
            )
            response.raise_for_status()
            tags = response.json()
            req.app.labeled_accounts_last_requested = dt.datetime.now().astimezone(
                dt.timezone.utc
            )
        except httpx.HTTPError:
            req.app.tags = None
            tags = None

        return tags


async def get_nodes(
    req: Request,
):
    if (
        (
            dt.datetime.now().astimezone(dt.timezone.utc) - req.app.nodes_last_requested
        ).total_seconds()
        < 9
    ) and (req.app.nodes):
        nodes: dict[NET, dict] = req.app.nodes
        # print("labeled_accounts from cache.")
    else:
        try:
            response = await req.app.httpx_client.get(
                f"{req.app.api_url}/v2/mainnet/misc/nodes"
            )
            response.raise_for_status()
            mainnet_nodes = response.json()
            req.app.nodes_last_requested = dt.datetime.now().astimezone(dt.timezone.utc)
        except httpx.HTTPError:
            mainnet_nodes = None

        try:
            response = await req.app.httpx_client.get(
                f"{req.app.api_url}/v2/testnet/misc/nodes"
            )
            response.raise_for_status()
            testnet_nodes = response.json()
            req.app.nodes_last_requested = dt.datetime.now().astimezone(dt.timezone.utc)
        except httpx.HTTPError:
            testnet_nodes = None

        nodes = {"mainnet": mainnet_nodes, "testnet": testnet_nodes}
        return nodes


# def get_memo_transfers(
#     req: Request,
# ):
#     if (
#         (
#             dt.datetime.now().astimezone(dt.timezone.utc)
#             - req.app.memo_transfers_last_requested
#         ).total_seconds()
#         < 10
#     ) and (req.app.memo_transfers):
#         set_memos: dict[str, list] = req.app.memo_transfers
#         # print("memo_transfers from cache.")
#     else:
#         if "net" in req.path_params:
#             db_to_use = (
#                 req.app.mongodb.testnet
#                 if req.path_params["net"] == "testnet"
#                 else req.app.mongodb.mainnet
#             )
#         set_memos = {
#             x["_id"]: x["tx_hashes"]
#             for x in db_to_use[Collections.memos_to_hashes].find({})
#         }
#         req.app.memo_transfers_last_requested = dt.datetime.now().astimezone(
#             dt.timezone.utc
#         )
#         req.app.memo_transfers = set_memos
#     return set_memos
