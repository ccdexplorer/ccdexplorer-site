from fastapi import Request

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


async def get_ccdscan(req: Request):
    return req.app.ccdscan


async def get_recurring(req: Request):
    return req.app.recurring


async def get_mongo_db(req: Request):
    return req.app.mongodb


async def get_mongo_motor(req: Request):
    return req.app.motormongo


async def get_grpcclient(req: Request):
    return req.app.grpcclient


async def get_tooter(req: Request):
    return req.app.tooter


async def get_server(req: Request):
    return req.app.server


async def get_state_response(req: Request):
    return req.app.state_response


async def get_cns_response(req: Request):
    return req.app.cns_response


async def get_accounts_response(req: Request):
    return req.app.accounts_response


async def get_user(req: Request):
    return req.app.user


# async def get_blocks_per_payday(mongodb: MongoDB):
#     result = {
#         x["date"]: (x["height_for_last_block"] - x["height_for_first_block"] + 1)
#         for x in mongodb.mainnet[Collections.paydays].find({})
#     }
#     return result


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


def get_exchange_rates(
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
        coll = req.app.mongodb.utilities[CollectionsUtilities.exchange_rates]

        req.app.exchange_rates = {x["token"]: x for x in coll.find({})}

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


def get_user_detailsv2(req: Request, token: str = None):
    get_and_save_user_from_collection(req=req)
    if not token:
        token = req.cookies.get("access-token")

    try:
        users_from_collection = req.app.users_from_collection
        user = users_from_collection.get(token)
    except AttributeError:
        user = None

    if user:
        if not type(user) == UserV2:
            user = UserV2(**user)

    return user


def get_credential_issuers(
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
        if "net" in req.path_params:
            db_to_use = (
                req.app.mongodb.testnet
                if req.path_params["net"] == "testnet"
                else req.app.mongodb.mainnet
            )
        else:
            db_to_use = req.app.mongodb.mainnet
        credential_issuers = [
            x["_id"] for x in db_to_use[Collections.credentials_issuers].find({})
        ]

        req.app.credential_issuers_last_requested = dt.datetime.now().astimezone(
            dt.timezone.utc
        )
        req.app.credential_issuers = credential_issuers

        print("credential_issuers from mongodb.")
    return credential_issuers


def get_contracts_with_tag_info(
    req: Request,
):
    req.app.contracts_with_tag_info = {}
    for net in NET:
        req.app.contracts_with_tag_info[net] = {}
        if net == NET.MAINNET:
            db_to_use = req.app.mongodb.mainnet
        elif net == NET.MAINNET:
            db_to_use = req.app.mongodb.testnet

        contracts_with_tag_info = {
            x["contract"]: MongoTypeTokensTag(**x)
            for x in db_to_use[Collections.pre_render].find(
                {"recurring_type": "contracts_to_tokens"}
            )
        }
        req.app.tokens_tags_last_requested = dt.datetime.now().astimezone(
            dt.timezone.utc
        )
        req.app.contracts_with_tag_info[net] = contracts_with_tag_info

        print(f"{len(contracts_with_tag_info.keys())} Tokens_tags from mongodb.")
    return req.app.contracts_with_tag_info


def get_token_addresses_with_markup(req: Request):
    if not req.app.contracts_with_tag_info:
        contracts_with_tag_info_both_nets = get_contracts_with_tag_info(req)
    else:
        contracts_with_tag_info_both_nets = req.app.contracts_with_tag_info

    # get exchange rates
    coll = req.app.mongodb.utilities[CollectionsUtilities.exchange_rates]
    exchange_rates = {x["token"]: x for x in coll.find({})}
    token_addresses_with_markup_both_nets = {}
    for net in NET:
        token_addresses_with_markup_both_nets[net] = {}
        if net == NET.MAINNET:
            db_to_use = req.app.mongodb.mainnet
        elif net == NET.MAINNET:
            db_to_use = req.app.mongodb.testnet

        # find fungible tokens
        fungible_contracts = [
            contract
            for contract, token_tag in contracts_with_tag_info_both_nets[net].items()
            if token_tag.token_type == "fungible"
        ]
        # now onto the token_addresses
        token_addresses_with_markup = {
            x["_id"]: MongoTypeTokenAddress(**x)
            for x in db_to_use[Collections.tokens_token_addresses_v2].find(
                {"contract": {"$in": fungible_contracts}}
            )
        }
        # queue = []
        for address in token_addresses_with_markup.keys():
            token_address_class = token_addresses_with_markup[address]
            if (
                token_address_class.contract
                in contracts_with_tag_info_both_nets[net].keys()
            ):
                token_address_class.tag_information = contracts_with_tag_info_both_nets[
                    net
                ][token_address_class.contract]
                if token_address_class.tag_information.token_type == "fungible":
                    if (
                        token_address_class.tag_information.get_price_from
                        in exchange_rates.keys()
                    ):
                        token_address_class.exchange_rate = exchange_rates[
                            token_address_class.tag_information.get_price_from
                        ]["rate"]
                    else:
                        token_address_class.exchange_rate = 0
            else:
                token_address_class.tag_information = None
            token_addresses_with_markup[address] = token_address_class
        token_addresses_with_markup_both_nets[net] = token_addresses_with_markup
    return token_addresses_with_markup_both_nets


def get_labeled_accounts(
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
        result = list(
            req.app.mongodb.utilities[CollectionsUtilities.labeled_accounts].find({})
        )
        labeled_accounts = {}
        for r in result:
            current_group = labeled_accounts.get(r["label_group"], {})
            current_group[r["_id"]] = r["label"]
            labeled_accounts[r["label_group"]] = current_group

        result = list(
            req.app.mongodb.utilities[
                CollectionsUtilities.labeled_accounts_metadata
            ].find({})
        )
        colors = {}
        descriptions = {}
        for r in result:
            colors[r["_id"]] = r.get("color")
            descriptions[r["_id"]] = r.get("description")

        req.app.labeled_accounts_last_requested = dt.datetime.now().astimezone(
            dt.timezone.utc
        )

        ### insert projects into tags
        # display_names
        projects_display_names = {
            x["_id"]: x["display_name"]
            for x in req.app.mongodb.utilities[CollectionsUtilities.projects].find({})
        }
        # account addresses
        project_account_addresses = list(
            req.app.mongodb.mainnet[Collections.projects].find(
                {"type": "account_address"}
            )
        )
        dd = {}
        for paa in project_account_addresses:
            dd[paa["account_address"]] = projects_display_names[paa["project_id"]]
        labeled_accounts["projects"] = dd

        # contract addresses
        project_contract_addresses = list(
            req.app.mongodb.mainnet[Collections.projects].find(
                {"type": "contract_address"}
            )
        )
        dd = {}
        for paa in project_contract_addresses:
            dd[paa["contract_address"]] = projects_display_names[paa["project_id"]]
        labeled_accounts["contracts"].update(dd)

        tags = {
            "labels": labeled_accounts,
            "colors": colors,
            "descriptions": descriptions,
        }
        req.app.tags = tags
    return tags


def get_memo_transfers(
    req: Request,
):
    if (
        (
            dt.datetime.now().astimezone(dt.timezone.utc)
            - req.app.memo_transfers_last_requested
        ).total_seconds()
        < 10
    ) and (req.app.memo_transfers):
        set_memos: dict[str, list] = req.app.memo_transfers
        # print("memo_transfers from cache.")
    else:
        if "net" in req.path_params:
            db_to_use = (
                req.app.mongodb.testnet
                if req.path_params["net"] == "testnet"
                else req.app.mongodb.mainnet
            )
        set_memos = {
            x["_id"]: x["tx_hashes"]
            for x in db_to_use[Collections.memos_to_hashes].find({})
        }
        req.app.memo_transfers_last_requested = dt.datetime.now().astimezone(
            dt.timezone.utc
        )
        req.app.memo_transfers = set_memos
    return set_memos
