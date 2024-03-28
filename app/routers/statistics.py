# ruff: noqa: F403, F405, E402, E501, E722, F401

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from app.classes.dressingroom import TransactionClassifier
from app.classes.Node_Baker import BakerStatus
from app.jinja2_helpers import *
from app.ajax_helpers import mongo_pagination_html_header
from app.env import *
from app.state.state import *
import requests
from typing import Optional, Union
import numpy as np
from bisect import bisect_right
from app.utils import user_string
from pydantic import ConfigDict
from ccdexplorer_fundamentals.user_v2 import UserV2, NotificationPreferences
from app.Recurring.recurring import Recurring
from ccdexplorer_fundamentals.cis import MongoTypeLoggedEvent
from ccdexplorer_fundamentals.mongodb import MongoDB
from pymongo import ASCENDING, DESCENDING
from datetime import timedelta
from ccdexplorer_fundamentals.tooter import Tooter, TooterType, TooterChannel
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_PoolInfo,
    CCD_CurrentPaydayStatus,
)
from altair import Chart
import pandas as pd
import altair as alt

alt.data_transformers.enable("vegafusion")

router = APIRouter()


def get_txs_for_impacted_address_cdex(mongodb: MongoDB):
    result = mongodb.mainnet_db["impacted_addresses"].find(
        {"impacted_address_canonical": "<9363,0>"}, projection={"_id": 0, "tx_hash": 1}
    )
    return [x["tx_hash"] for x in list(result)]


def get_txs_for_impacted_address_arabella(mongodb: MongoDB):
    result = mongodb.mainnet_db["impacted_addresses"].find(
        {"impacted_address_canonical": "<9337,0>"}, projection={"_id": 0, "tx_hash": 1}
    )
    return [x["tx_hash"] for x in list(result)]


class ReportingActionType(str, Enum):
    deposit = "Deposit"
    swap = "Swap"
    withdraw = "Withdraw"
    mint = "Mint"
    burn = "Burn"
    none = "None"


class ReportingSubject(str, Enum):
    Concordex = "Concordex"
    Arabella = "Arabella"


class ClassifiedTransaction(BaseModel):
    tx_hash: str
    logged_events: list[MongoTypeLoggedEvent]
    block_height: int
    addresses: Optional[set] = None
    date: Optional[str] = None
    action_type: Optional[ReportingActionType] = None


class ReportingUnit(BaseModel):
    tx_hash: str
    date: str
    fungible_token: str
    amount_in_local_currency: float
    amount_in_usd: float
    action_type: str


class ReportingAddresses(BaseModel):
    tx_hash: str
    date: str
    addresses: str


class ReportingOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    txs_by_action_type: dict  # [ReportingActionType: list[ClassifiedTransaction]]
    # output: list
    # df_accounts: dict
    # df_raw: pd.DataFrame
    # df_output_action_types: dict  # [str:pd.DataFrame]
    # df_output_fungible_token: dict  # [str:pd.DataFrame]


def address_exists_and_is_account(address: Union[None, str]):
    if not address:
        return False
    else:
        if len(address) > 20:
            return True
        else:
            return False


def classify_tx_as_swap_or_withdraw(classified_tx: ClassifiedTransaction):
    log_0_to = classified_tx.logged_events[0].result.get("to_address")
    log_0_from = classified_tx.logged_events[0].result.get("from_address")
    log_1_to = classified_tx.logged_events[1].result.get("to_address")

    if address_exists_and_is_account(log_0_to) and address_exists_and_is_account(
        log_1_to
    ):
        classified_tx.action_type = ReportingActionType.withdraw
    else:
        if (
            classified_tx.logged_events[0].event_type == "mint_event"
            and address_exists_and_is_account(log_1_to)
            or address_exists_and_is_account(log_0_from)
            and address_exists_and_is_account(log_1_to)
            or address_exists_and_is_account(log_0_from)
            and classified_tx.logged_events[1].event_type == "burn_event"
        ):
            classified_tx.action_type = ReportingActionType.swap
    return classified_tx


def find_date_for_height(heights, block_end_of_day_dict, height):
    found_index = bisect_right(heights, height)
    # meaning it's today...
    if found_index == len(heights):
        return f"{dt.datetime.now():%Y-%m-%d}"
    else:
        return block_end_of_day_dict[heights[found_index]]


def find_date_and_date_str_for_height(heights, block_end_of_day_dict, height):
    found_index = bisect_right(heights, height)
    # meaning it's today...
    if found_index == len(heights):
        return f"{dt.datetime.utcnow():%Y-%m-%d}"
    else:
        return block_end_of_day_dict[heights[found_index]]


def add_date_to_tx(tx: ClassifiedTransaction, heights, block_end_of_day_dict):
    date = find_date_and_date_str_for_height(
        heights, block_end_of_day_dict, tx.block_height
    )
    tx.date = date
    return tx


# def process_txs_for_analytics(
#     txs_by_action_type, token_addresses_with_markup, exchange_rates
# ):
#     # token_addresses_with_markup = get_token_addresses_with_markup()
#     output = []
#     accounts = []

#     for action_type in ReportingActionType:
#         txs_per_action_type = txs_by_action_type[action_type]
#         for tx in txs_per_action_type:
#             tx: ClassifiedTransaction
#             r = tx.logged_events[0]
#             output, accounts = append_logged_event(
#                 token_addresses_with_markup,
#                 output,
#                 accounts,
#                 action_type,
#                 tx,
#                 r,
#                 exchange_rates,
#             )

#             if tx.action_type == ReportingActionType.withdraw:
#                 r = tx.logged_events[1]
#                 output, accounts = append_logged_event(
#                     token_addresses_with_markup,
#                     output,
#                     accounts,
#                     action_type,
#                     tx,
#                     r,
#                     exchange_rates,
#                 )

#     df = pd.DataFrame([x.model_dump() for x in output])
#     df["date"] = pd.to_datetime(df["date"])

#     df_a = pd.DataFrame([x.model_dump() for x in accounts])
#     df_a["date"] = pd.to_datetime(df_a["date"])

#     df_output_action_types = {}
#     df_output_fungible_token = {}
#     df_accounts = {}
#     for letter in ["D", "W", "M"]:
#         df_output_action_types[letter] = (
#             df.groupby([pd.Grouper(key="date", axis=0, freq=letter), "action_type"])
#             .sum()
#             .reset_index()
#         )
#         # df_output_action_types[letter]["date"] = str(
#         #     df_output_action_types[letter]["date"]
#         # )

#         df_output_fungible_token[letter] = (
#             df.groupby([pd.Grouper(key="date", axis=0, freq=letter), "fungible_token"])
#             .sum()
#             .reset_index()
#         )
#         # df_output_fungible_token[letter]["date"] = str(
#         #     df_output_fungible_token[letter]["date"]
#         # )

#         df_accounts[letter] = (
#             df_a.groupby([pd.Grouper(key="date", axis=0, freq=letter)])["addresses"]
#             .agg(",".join)
#             .reset_index()
#         )
#         df_accounts[letter]["addresses"] = df_accounts[letter]["addresses"].str.split(
#             ","
#         )
#         df_accounts[letter]["addresses"] = df_accounts[letter]["addresses"].apply(set)
#         df_accounts[letter]["addresses_unique"] = df_accounts[letter][
#             "addresses"
#         ].apply(len)
#         columns = ["date", "addresses_unique"]
#         df_accounts[letter] = pd.DataFrame(df_accounts[letter], columns=columns)
#         # df_accounts[letter]["date"] = str(df_accounts[letter]["date"])

#         # df.groupby('col')['val'].agg('-'.join)
#     return ReportingOutput(
#         df_raw=df,
#         txs_by_action_type=txs_by_action_type,
#         output=output,
#         df_accounts=df_accounts,
#         df_output_action_types=df_output_action_types,
#         df_output_fungible_token=df_output_fungible_token,
#     )


# def append_logged_event(
#     token_addresses_with_markup,
#     output: list[ReportingUnit],
#     accounts: list[ReportingAddresses],
#     action_type: ReportingActionType,
#     tx: ClassifiedTransaction,
#     r: MongoTypeLoggedEvent,
#     exchange_rates,
# ):
#     token_address_with_markup: MongoTypeTokenAddress = token_addresses_with_markup.get(
#         r.token_address
#     )
#     if not token_address_with_markup:
#         console.log(f"Can't find {r.token_address} in token_addresses_with_markup!!!")
#         return output, accounts

#     fungible_token = token_address_with_markup.tag_information.id
#     if fungible_token[0] == "w":
#         fungible_token = fungible_token[1:]
#     if int(r.result["token_amount"]) > 0:
#         real_token_amount = int(r.result["token_amount"]) * (
#             math.pow(10, -token_address_with_markup.tag_information.decimals)
#         )

#         if exchange_rates.get(fungible_token):
#             if tx.date in exchange_rates[fungible_token]:
#                 exchange_rate_for_day = exchange_rates[fungible_token][tx.date]
#                 dd = {
#                     "tx_hash": tx.tx_hash,
#                     "date": tx.date,
#                     "fungible_token": fungible_token,
#                     "amount_in_local_currency": real_token_amount,
#                     "amount_in_usd": real_token_amount * exchange_rate_for_day,
#                     "action_type": action_type.value,
#                 }
#                 # print (dd)
#                 output.append(ReportingUnit(**dd))
#                 if len(tx.addresses) > 0:
#                     accounts.append(
#                         ReportingAddresses(
#                             **{
#                                 "tx_hash": tx.tx_hash,
#                                 "date": tx.date,
#                                 "addresses": ", ".join(tx.addresses),
#                             }
#                         )
#                     )
#     return output, accounts


def add_tx_addresses(event: MongoTypeLoggedEvent, addresses: set):
    _to = event.result.get("to_address")
    if _to:
        if len(_to) > 20:
            addresses.add(_to)

    _from = event.result.get("from_address")
    if _from:
        if len(_from) > 20:
            addresses.add(_from)

    return addresses


def process_txs_for_action_type_classification(
    cdex_txs: list[str],
    reporting_subject: ReportingSubject,
    mongodb: MongoDB,
    heights,
    block_end_of_day_dict,
):
    validated_txs = {}
    txs_by_action_type: dict[ReportingActionType : list[ClassifiedTransaction]] = {}
    for action_type in ReportingActionType:
        txs_by_action_type[action_type]: list[ClassifiedTransaction] = []  # type: ignore

    # get all logged events from transactions on impacted address <9363,0>
    # note: transactions without logged events are not retrieved.
    all_logged_events_for_tx_hashes = [
        MongoTypeLoggedEvent(**x)
        for x in mongodb.mainnet_db["tokens_logged_events"].aggregate(
            [
                {"$match": {"tx_hash": {"$in": cdex_txs}}},
                {"$sort": {"ordering": ASCENDING}},
            ]
        )
    ]

    tx_hashes_from_events = []

    # groupby transaction hash, output in dict classified_txs
    for event in all_logged_events_for_tx_hashes:
        addresses = add_tx_addresses(event, set())
        tx_hashes_from_events.append(event.tx_hash)
        classified_tx = validated_txs.get(event.tx_hash)
        if not classified_tx:
            validated_txs[event.tx_hash] = ClassifiedTransaction(
                tx_hash=event.tx_hash,
                logged_events=[event],
                block_height=event.block_height,
                addresses=addresses,
            )
        else:
            classified_tx: ClassifiedTransaction
            addresses = add_tx_addresses(event, classified_tx.addresses)
            classified_tx.addresses = addresses
            classified_tx.logged_events.append(event)
            validated_txs[event.tx_hash] = classified_tx

    # now all transactions have been been validated, time to classify to action type
    for classified_tx in validated_txs.values():
        classified_tx.action_type = ReportingActionType.none
        classified_tx = add_date_to_tx(classified_tx, heights, block_end_of_day_dict)

        if reporting_subject == ReportingSubject.Concordex:
            if len(classified_tx.logged_events) == 1:
                classified_tx.action_type = ReportingActionType.deposit

            elif len(classified_tx.logged_events) > 1:
                classified_tx = classify_tx_as_swap_or_withdraw(classified_tx)

        elif reporting_subject == ReportingSubject.Arabella:
            if classified_tx.logged_events[0].event_type == "mint_event":
                classified_tx.action_type = ReportingActionType.mint

            if classified_tx.logged_events[0].event_type == "burn_event":
                classified_tx.action_type = ReportingActionType.burn

        txs_by_action_type[classified_tx.action_type].append(classified_tx)
    return txs_by_action_type, tx_hashes_from_events


def get_analytics_for_platform(
    reporting_subject: ReportingSubject,
    mongodb: MongoDB,
    token_addresses_with_markup,
    exchange_rates,
    request: Request,
):
    if (
        (
            dt.datetime.now().astimezone(dt.timezone.utc)
            - request.app.reporting_output_last_requested
        ).total_seconds()
        < 60 * 5
    ) and (request.app.reporting_output.get(reporting_subject)):
        reporting_output = request.app.reporting_output[reporting_subject]

    else:
        result = list(
            mongodb.mainnet[Collections.blocks_per_day].find(
                filter={},
                projection={
                    "_id": 0,
                    "date": 1,
                    "height_for_last_block": 1,
                    "slot_time_for_last_block": 1,
                },
            )
        )
        block_end_of_day_dict = {x["height_for_last_block"]: x["date"] for x in result}
        heights = list(block_end_of_day_dict.keys())

        if reporting_subject == ReportingSubject.Concordex:
            tx_hashes = get_txs_for_impacted_address_cdex(mongodb)
        elif reporting_subject == ReportingSubject.Arabella:
            tx_hashes = get_txs_for_impacted_address_arabella(mongodb)

        (
            txs_by_action_type,
            _,
        ) = process_txs_for_action_type_classification(
            tx_hashes, reporting_subject, mongodb, heights, block_end_of_day_dict
        )
        reporting_output = ReportingOutput(txs_by_action_type=txs_by_action_type)
        request.app.reporting_output[reporting_subject] = reporting_output
        request.app.reporting_output_last_requested = dt.datetime.now().astimezone(
            dt.timezone.utc
        )
    return reporting_output


@router.get("/{net}/statistics", response_class=HTMLResponse)
async def statistics(
    request: Request,
    net: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    tooter: Tooter = Depends(get_tooter),
):
    user: UserV2 = get_user_detailsv2(request)

    if net == "mainnet":
        try:
            t = requests.get(
                "https://raw.githubusercontent.com/sderuiter/concordium-network-statistics/main/network-summary.json",
                verify=False,
            )
            t = t.json()
            baker_count = t["baker_count"]
            account_count = t["account_count"]
            free_float = t["free_float"]
        except:
            baker_count = 0
            account_count = 0
            free_float = 0
        # baker_count = len(recurring.bakers_classified[BakerStatus.Active])
        baker_count = len(recurring.all_bakers_by_baker_id)
        return templates.TemplateResponse(
            "statistics/statistics-clean.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "account_count": account_count,
                "baker_count": baker_count,
                "free_float": free_float,
                "user": user,
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


#########################
### TAKE 2


def replace_short_strings(string):
    if len(string) < 5:
        return ""
    else:
        return string


@router.get(
    "/ajax_bridges_and_dexes/{rep_subject}/{output_type}/{period}/{width}",
    response_class=Response,
)
async def bridges_and_dexes_graph(
    request: Request,
    rep_subject: str,
    output_type: str,
    period: str,
    width: int,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    tooter: Tooter = Depends(get_tooter),
):
    # user: UserV2 = get_user_detailsv2(request)

    reporting_subject = ReportingSubject(rep_subject.capitalize())
    all_data = get_all_data_for_bridges_and_dexes(
        "statistics_bridges_and_dexes", rep_subject, mongodb
    )
    d_date = get_statistics_date(mongodb)

    action_types_list = []
    fungible_tokens_list = []
    unique_addresses_list = []
    tvl_list = []
    tvl = 0
    start_date = all_data[0]["date"]
    end_date = all_data[-1]["date"]
    domain = [
        dateutil.parser.parse(start_date),
        dateutil.parser.parse(end_date),
    ]

    for day in all_data:
        if len(day["action_types_for_day"]) > 0:
            for action_type in day["action_types_for_day"]:
                action_types_list.append(
                    {
                        "date": day["date"],
                        "action_type": action_type["action_type"],
                        "amount_in_usd": action_type["amount_in_usd"],
                    }
                )
                # TVL
                if reporting_subject == ReportingSubject.Arabella:
                    if action_type["action_type"] == "Mint":
                        tvl += action_type["amount_in_usd"]
                    if action_type["action_type"] == "Withdraw":
                        tvl -= action_type["amount_in_usd"]

                if reporting_subject == ReportingSubject.Concordex:
                    if action_type["action_type"] == "Deposit":
                        tvl += action_type["amount_in_usd"]
                    if action_type["action_type"] == "Withdraw":
                        tvl -= action_type["amount_in_usd"]

            tvl_list.append({"date": day["date"], "tvl_in_usd": tvl})

        if len(day["fungible_tokens_for_day"]) > 0:
            for fungible_token in day["fungible_tokens_for_day"]:
                fungible_tokens_list.append(
                    {
                        "date": day["date"],
                        "fungible_token": fungible_token["fungible_token"],
                        "amount_in_usd": fungible_token["amount_in_usd"],
                    }
                )
        if len(day["unique_addresses_for_day"]) > 0:
            for address in day["unique_addresses_for_day"]:
                unique_addresses_list.append(
                    {"date": day["date"], "unique_address": address}
                )
        # else:
        #     unique_addresses_list.append({"date": day["date"], "unique_address": None})

    if period == "Daily":
        letter = "D"
        tooltip = "Day"
    if period == "Weekly":
        letter = "W"
        tooltip = "Week"
    if period == "Monthly":
        letter = "ME"
        tooltip = "Month"

    rng_action_types = [
        "#AE7CF7",
        "#70B785",
        "#6E97F7",
        "#EE9B54",
    ]

    rng_tokens = [
        "#DC5050",
        "#FBCD29",
        "#33C364",
        "#2485DF",
        "#7939BA",
        "#E87E90",
        "#F6DB9A",
        "#8BE7AA",
        "#65A4DD",
        "#B37CDF",
    ]

    if output_type == "action-type":
        df_action_types = pd.DataFrame(action_types_list)
        df_action_types["date"] = pd.to_datetime(df_action_types["date"])
        df_output_action_types = (
            df_action_types.groupby(
                [pd.Grouper(key="date", axis=0, freq=letter), "action_type"]
            )
            .sum()
            .reset_index()
        )
        dates = df_output_action_types["date"].to_list()
        domain = [
            dates[0],
            dates[-1],
        ]
        base = alt.Chart(df_output_action_types).encode(
            x=alt.X("date:T", scale=alt.Scale(domain=domain))
        )

        chart = base.mark_area(interpolate="monotone").encode(
            y=alt.Y("amount_in_usd:Q", title="USD"),
            tooltip=[
                alt.Tooltip("date:T", title="Date"),
                alt.Tooltip("action_type:O", title="Action Type"),
                alt.Tooltip("amount_in_usd:Q", title="Amount (USD)", format=",.0f"),
            ],
            color=alt.Color(
                "action_type",
                title="Action Type",
                scale=alt.Scale(range=rng_action_types),
                legend=alt.Legend(orient="bottom"),
                sort=alt.EncodingSortField(
                    "amount_in_usd", op="sum", order="descending"
                ),
            ),
        )
        df_unique_addresses = pd.DataFrame(unique_addresses_list)
        df_unique_addresses["date"] = pd.to_datetime(df_unique_addresses["date"])
        df_unique_addresses.fillna("", inplace=True)
        df_accounts = (
            df_unique_addresses.groupby([pd.Grouper(key="date", axis=0, freq=letter)])[
                "unique_address"
            ]
            .agg(",".join)
            .reset_index()
        )
        df_accounts["unique_address"] = df_accounts["unique_address"].str.split(",")
        df_accounts["unique_address"] = df_accounts["unique_address"].apply(set)
        df_accounts["unique_address"] = df_accounts["unique_address"].apply(list)
        df_accounts["unique_address"] = df_accounts["unique_address"].apply(
            lambda x: "" if x == [""] else x
        )

        df_accounts["unique_address"] = df_accounts["unique_address"].apply(len)

        users_line = (
            alt.Chart(df_accounts.interpolate())
            .mark_line(point=True, opacity=0.6, interpolate="monotone")
            .encode(
                x=alt.X("date:T", scale=alt.Scale(domain=domain)),
                y=alt.Y("unique_address:Q", title=f"Unique {period} Addresses"),
                tooltip=[
                    alt.Tooltip("date:T", title="Date"),
                    alt.Tooltip(
                        "unique_address:Q",
                        title=f"Unique {period} Addresses",
                        format=",.0f",
                    ),
                ],
            )
        )
        UA = "UAW"
        if period == "Daily":
            UA = "UAD"
        if period == "Weekly":
            UA = "UAW"
        if period == "Monthly":
            UA = "UAM"

        chart_by_action_type = (
            (chart + users_line)
            .resolve_scale(y="independent")
            .properties(
                width=width * 0.75 if width < 400 else width,
                title={
                    "text": f"{reporting_subject.value} Usage by Action Type (with {UA})",
                    "subtitle": f"Grouped {period}, {d_date}",
                },
            )
            .to_json(format="vega")
        )
        return chart_by_action_type

    if output_type == "token":
        df_fungible_tokens = pd.DataFrame(fungible_tokens_list)
        df_fungible_tokens["date"] = pd.to_datetime(df_fungible_tokens["date"])
        df_output_fungible_token = (
            df_fungible_tokens.groupby(
                [pd.Grouper(key="date", axis=0, freq=letter), "fungible_token"]
            )
            .sum()
            .reset_index()
        )
        dates = df_output_fungible_token["date"].to_list()
        domain = [
            dates[0],
            dates[-1],
        ]
        chart_by_token = (
            alt.Chart(df_output_fungible_token)
            .mark_area(interpolate="monotone")
            .encode(
                x=alt.X(
                    "date:T", scale=alt.Scale(domain=domain)
                ),  # , scale=alt.Scale(domain=list(domain_pd))),
                tooltip=[
                    alt.Tooltip("date:T", title="Date"),
                    alt.Tooltip("amount_in_usd:Q", title="Amount (USD)", format=",.0f"),
                    alt.Tooltip("fungible_token:O", title="Fungible Token"),
                ],
                y=alt.Y(
                    "amount_in_usd:Q", title="USD"
                ),  # , scale=alt.Scale(zero=False, type='log')),
                color=alt.Color(
                    "fungible_token:O",
                    scale=alt.Scale(range=rng_tokens),
                    legend=alt.Legend(orient="bottom", columns=2),
                    title="Fungible Token",
                    sort=alt.EncodingSortField(
                        "amount_in_usd", op="sum", order="descending"
                    ),
                ),
            )
            .properties(
                width=width * 0.75 if width < 400 else width,
                title={
                    "text": f"{reporting_subject.value} Usage by Fungible Token",
                    "subtitle": f"Grouped {period}, {d_date}",
                },
            )
        ).to_json(format="vega")

        return chart_by_token

    if output_type == "tvl":
        df_tvl = pd.DataFrame(tvl_list)
        df_tvl["date"] = pd.to_datetime(df_tvl["date"])
        # now find all dates in the grouped dfs. This list of dates will be the list we use
        # to lookup the correct TVL values.
        # grouped_dates = df_output_action_types["date"].to_list()
        # mask = df_tvl["date"].isin(grouped_dates)
        # df_tvl = df_tvl[mask]
        df_tvl_for_chart = (
            df_tvl.groupby([pd.Grouper(key="date", axis=0, freq=letter)])
            .mean()
            .reset_index()
        )

        dates = df_tvl_for_chart["date"].to_list()
        domain = [
            dates[0],
            dates[-1],
        ]
        chart_by_tvl = (
            alt.Chart(df_tvl_for_chart.interpolate())
            .mark_line(point=True, interpolate="monotone", color="#AE7CF7", size=3)
            .encode(
                x=alt.X(
                    "date:T", scale=alt.Scale(domain=domain)
                ),  # , scale=alt.Scale(domain=list(domain_pd))),
                tooltip=[
                    alt.Tooltip("date:T", title="Date"),
                    alt.Tooltip("tvl_in_usd:Q", title="TVL (USD)", format=",.0f"),
                ],
                y=alt.Y("tvl_in_usd:Q", title="USD"),
            )
            .properties(
                width=width * 0.75 if width < 400 else width,
                title={
                    "text": f"{reporting_subject.value} Mean Total Value Locked (TVL)",
                    "subtitle": f"Grouped {period}, {d_date}",
                },
            )
        ).to_json(format="vega")

        return chart_by_tvl


#########################


def mongo_logged_events_html_header(
    total_len_rows,
    current_page,
    tx_tabs,
    tx_tabs_active,
    word="event",
):
    html = ""
    html += mongo_pagination_html_header(total_len_rows, current_page, word)
    html += '<ul class="nav nav-tabs ms-1 me-1" id="myTab" role="tablist" style="padding-top:10px;">'

    for tab in ReportingActionType:
        if len(tx_tabs[tab]) > 0:
            active_str = "active" if tx_tabs_active[tab] else ""
            html += (
                '<li class="nav-item" role="presentation">'
                f'<button class="nav-link small ps-2 pe-2 {active_str}" id="{tab.value}-tab" data-bs-toggle="tab" data-bs-target="#{tab.value}" type="button" role="tab" aria-controls="{tab.value}-tab" aria-selected="true"><small>{tab.value} ({len(tx_tabs[tab])})</small></button>'
                "</li>"
            )

    html += "</ul>\n" '<div class="tab-content" id="myTabContent">\n'

    return html


def process_logged_events_to_HTML(rows, tab_string: str, active: bool):
    active_str = "active" if active else ""

    # header for the specific tab
    html = f'<div class="tab-pane fade show {active_str} " style="padding-top: 10px;" id="{tab_string}" role="tabpanel" aria-labelledby="{tab_string}-tab">\n'

    html += "<table class='table-sm table-striped'>"
    # the transactions
    for row in rows:
        html += row

    # closing the header
    html += '</table><!-- class="tab-pane fade -->\n' "</div>\n"

    return html


@router.get(
    "/ajax_events/{net}/statistics/{reporting_subject}/{requested_page}/{total_rows}",
    response_class=Response,
)
async def statistics_ajax_reporting_subject_events_logged_events(
    request: Request,
    net: str,
    reporting_subject: str,
    requested_page: int,
    total_rows: int,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    tooter: Tooter = Depends(get_tooter),
    # contracts_with_tag_info: dict = Depends(get_contracts_with_tag_info),
    token_addresses_with_markup: dict = Depends(get_token_addresses_with_markup),
    exchange_rates: dict = Depends(get_historical_rates),
):
    # user: UserV2 = get_user_detailsv2(request)
    limit = 20
    reporting_subject = ReportingSubject(reporting_subject.capitalize())
    reporting_output = get_analytics_for_platform(
        reporting_subject, mongodb, token_addresses_with_markup, exchange_rates, request
    )

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

    tx_tabs = {}
    tx_tabs_active = {}
    for action in ReportingActionType:
        tx_tabs[action] = []

    # add all classified_txs up to apply skip / limit to
    all_logged_events = []
    for _, classified_txs in reporting_output.txs_by_action_type.items():
        for cl_tx in classified_txs:
            for logged_event in cl_tx.logged_events:
                all_logged_events.append(
                    {
                        "logged_event": logged_event,
                        "action_type": cl_tx.action_type,
                        "date": cl_tx.date,
                    }
                )

    all_logged_events = sorted(
        all_logged_events, reverse=True, key=lambda x: x["logged_event"].block_height
    )
    logged_events_this_page = all_logged_events[skip : (skip + limit)]

    for event_dict in logged_events_this_page:
        tx_tabs[event_dict["action_type"]].append(
            {"logged_event": event_dict["logged_event"], "date": event_dict["date"]}
        )

    tab_selected_to_be_active = False
    for tab in ReportingActionType:
        tx_tabs_active[tab] = False
        if (not tab_selected_to_be_active) and (len(tx_tabs[tab]) > 0):
            tab_selected_to_be_active = True
            tx_tabs_active[tab] = True

    html = mongo_logged_events_html_header(
        len(all_logged_events),
        requested_page,
        tx_tabs,
        tx_tabs_active,
    )

    for tab in ReportingActionType:
        # if reporting_subject == ReportingSubject.Arabella:
        #     active_str = ""
        #     if (tab.value == "Mint") and (len(tx_tabs[tab]) > 0):
        #         active_str = "active"
        #     if (tab.value == "Burn") and (len(tx_tabs[tab]) > 0):
        #         active_str = "active"

        # else:
        #     active_str = "active" if tab.value == "Deposit" else ""
        active_str = "active" if tx_tabs_active[tab] else ""
        if len(tx_tabs[tab]) > 0:
            html += f'<div class="tab-pane fade show {active_str} " style="padding-top: 10px;" id="{tab.value}" role="tabpanel" aria-labelledby="{tab.value}-tab">'
            html += templates.get_template(
                "statistics/statistics-logged-events.html"
            ).render(
                {
                    "net": net,
                    "logged_events": tx_tabs[tab],
                    "token_addresses_with_markup": token_addresses_with_markup,
                }
            )

    # html += transactions_html_footer()
    return html


@router.get("/{net}/statistics/{reporting_subject}", response_class=HTMLResponse)
async def statistics_reporting_subject(
    request: Request,
    net: str,
    reporting_subject: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    tooter: Tooter = Depends(get_tooter),
    # contracts_with_tag_info: dict = Depends(get_contracts_with_tag_info),
    # token_addresses_with_markup: dict = Depends(get_token_addresses_with_markup),
    # exchange_rates: dict = Depends(get_historical_rates),
):
    user: UserV2 = get_user_detailsv2(request)
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "user": user,
            },
        )
    print(f"{net=}")
    return templates.TemplateResponse(
        "statistics/statistics-bridge-dex-v2.html",
        {
            "env": request.app.env,
            "net": net,
            "request": request,
            "user": user,
            "reporting_subject": reporting_subject,
        },
    )


class AnalysisType(Enum):
    statistics_daily_holders = "statistics_daily_holders"
    statistics_daily_limits = "statistics_daily_limits"
    statistics_network_summary = "statistics_network_summary"
    statistics_classified_pools = "statistics_classified_pools"


def get_all_data_for_analysis(analysis: str, mongodb: MongoDB) -> list[str]:
    return [
        x
        for x in mongodb.mainnet[Collections.statistics]
        .find({"type": analysis}, {"_id": 0, "type": 0})
        .sort("date", ASCENDING)
    ]


def get_all_data_for_bridges_and_dexes(
    analysis: str, reporting_subject: str, mongodb: MongoDB
) -> list[str]:
    pipeline = [
        {"$match": {"type": analysis}},
        {"$match": {"reporting_subject": reporting_subject}},
        {
            "$project": {
                "_id": 0,
                "type": 0,
                "reporting_subject": 0,
            }
        },
        {"$sort": {"date": 1}},
    ]
    return list(mongodb.mainnet[Collections.statistics].aggregate(pipeline))


def generate_dates_from_start_until_end(start: str, end: str):
    start_date = dateutil.parser.parse(start)
    end_date = dateutil.parser.parse(end)
    date_range = []

    current_date = start_date
    while current_date <= end_date:
        date_range.append(current_date.strftime("%Y-%m-%d"))
        current_date += timedelta(days=1)

    return date_range


def get_all_data_for_analysis_limited(
    analysis: str, mongodb: MongoDB, dates_to_include: list[str]
) -> list[str]:
    pipeline = [
        {"$match": {"date": {"$in": dates_to_include}}},
        {"$match": {"type": analysis}},
        {"$project": {"_id": 0, "type": 0}},
        {"$sort": {"date": 1}},
    ]
    result = mongodb.mainnet[Collections.statistics].aggregate(pipeline)
    return [x for x in result]


def get_statistics_date(mongodb: MongoDB) -> str:
    result = mongodb.mainnet[Collections.helpers].find_one(
        {"_id": "last_known_nightly_accounts"}
    )
    return result["date"]


@router.get(
    "/{net}/ajax_statistics/statistics_daily_holders/{width}", response_class=Response
)
async def statistics_daily_holders(
    request: Request,
    net: str,
    width: int,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request)
    analysis = "statistics_daily_holders"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "user": user,
            },
        )

    all_data = get_all_data_for_analysis(analysis, mongodb)
    d_date = get_statistics_date(mongodb)
    df = pd.DataFrame(all_data)
    base = alt.Chart(df).encode(alt.X("date:T", axis=alt.Axis(title=None)))

    line = base.mark_bar(opacity=1, strokeWidth=5, color="#549FF2").encode(
        alt.Y(
            "count_above_1M",
            axis=alt.Axis(
                title="Count of Accounts holding > 1M CCD", titleColor="#549FF2"
            ),
        )
    )
    chart = line.properties(
        width="container",
        height=350,
        title={
            "text": "Count of Accounts holding > 1M CCD",
            "subtitle": f"{d_date}",
        },
    )

    return chart.to_json(format="vega")


@router.get(
    "/{net}/ajax_statistics/statistics_daily_limits/{width}", response_class=Response
)
async def statistics_daily_limits(
    request: Request,
    net: str,
    width: int,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request)
    analysis = "statistics_daily_limits"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "user": user,
            },
        )

    all_data = get_all_data_for_analysis(analysis, mongodb)
    d_date = get_statistics_date(mongodb)
    df = pd.DataFrame(all_data)
    df.rename(
        columns={
            "amount_to_make_top_100": "Top 100",
            "amount_to_make_top_250": "Top 250",
        },
        inplace=True,
    )
    melt = df.melt("date", var_name="limit_amount", value_name="value")
    # print(melt)
    base = alt.Chart(melt).encode(alt.X("date:T", axis=alt.Axis(title=None)))

    rng = ["#AE7CF7", "#70B785"]  # , '#549FF2', '#EBBC90']
    line = base.mark_line(opacity=1, strokeWidth=2).encode(
        alt.Y("value:Q", axis=alt.Axis(title="Amount (CCD)")),
        alt.Color(
            "limit_amount:O",
            scale=alt.Scale(range=rng),
            title="Amount needed for...",
        ),
    )

    chart: Chart = line.properties(
        width="container",
        # width=400,
        height=350,
        title={
            "text": "Amounts of CCD needed to make top 100/250",
            "subtitle": f"{d_date}",
        },
    ).configure_legend(
        orient="bottom",
        direction="vertical",
        fillColor="white",
        padding=5,
        strokeColor="gray",
        labelFontSize=9,
    )

    return chart.to_json(format="vega")


@router.get(
    "/{net}/ajax_statistics/statistics_network_summary_validator_count/{width}",
    response_class=Response,
)
async def statistics_network_summary_validator_count(
    request: Request,
    net: str,
    width: int,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request)
    analysis = "statistics_network_summary"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "user": user,
            },
        )

    all_data = get_all_data_for_analysis(analysis, mongodb)
    d_date = get_statistics_date(mongodb)
    df = pd.DataFrame(all_data)
    validators = (
        alt.Chart(df)
        .mark_line(color="#70B785", opacity=0.8)
        .encode(
            x=alt.X("date:T"),
            y=alt.Y("validator_count", title="Count of Validators"),
            # color='transaction_type'
        )
    )
    chart = validators.properties(
        width="container",
        # width=400,
        height=350,
        title={
            "text": "Registered Validators",
            "subtitle": f"{d_date}",
        },
    )

    return chart.to_json(format="vega")


@router.get(
    "/{net}/ajax_statistics/statistics_network_summary_accounts_per_day/{width}",
    response_class=Response,
)
async def statistics_network_summary_accounts_per_day(
    request: Request,
    net: str,
    width: int,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request)
    analysis = "statistics_network_summary"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "user": user,
            },
        )

    all_data = get_all_data_for_analysis(analysis, mongodb)
    d_date = get_statistics_date(mongodb)
    df_per_day = pd.DataFrame(all_data)
    df_per_day["d_count_accounts"] = df_per_day["account_count"] - df_per_day[
        "account_count"
    ].shift(+1)

    df_per_day = df_per_day.dropna()

    df_per_day.rename(
        columns={"d_count_accounts": "growth", "account_count": "level"}, inplace=True
    )

    base = alt.Chart(df_per_day).encode(alt.X("date:T", axis=alt.Axis(title=None)))

    line = base.mark_bar(opacity=1, strokeWidth=5, color="#549FF2").encode(
        alt.Y("growth", axis=alt.Axis(title="Account Growth", titleColor="#549FF2"))
    )

    bar = base.mark_line(opacity=0.6, stroke="#AE7CF7").encode(
        alt.Y("level", axis=alt.Axis(title="Accounts on Chain", titleColor="#AE7CF7"))
    )
    chart: Chart = (
        alt.layer(bar, line)
        .resolve_scale(y="independent")
        .properties(
            width="container",
            # width=400,
            height=350,
            title={
                "text": "Accounts Active and Growth per day",
                "subtitle": f"{d_date}",
            },
        )
    )

    return chart.to_json(format="vega")


@router.get(
    "/{net}/ajax_statistics/statistics_classified_pools_open_pool_count/{width}",
    response_class=Response,
)
async def statistics_classified_pools_open_pool_count(
    request: Request,
    net: str,
    width: int,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request)
    analysis = "statistics_classified_pools"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "user": user,
            },
        )

    all_data = get_all_data_for_analysis(analysis, mongodb)
    d_date = get_statistics_date(mongodb)
    df_pools = pd.DataFrame(all_data)
    df_pools = df_pools[
        [
            "date",
            "open_pool_count",
            "delegator_count",
            "delegator_avg_stake",
            "delegator_avg_count_per_pool",
        ]
    ]

    base = alt.Chart(df_pools).encode(alt.X("date:T", title=None))
    open_pool_count = base.mark_area(
        line={"color": "#80B589"},
        color=alt.Gradient(
            gradient="linear",
            stops=[
                alt.GradientStop(color="white", offset=0),
                alt.GradientStop(color="#80B589", offset=1),
            ],
            x1=1,
            x2=1,
            y1=1,
            y2=0,
        ),
    ).encode(alt.Y("open_pool_count:Q", title=None))
    chart = open_pool_count.properties(
        width="container",
        # width = 400,
        height=150,
        title={
            "text": "# Open Pools",
            "subtitle": f"{d_date}",
        },
    )
    return chart.to_json(format="vega")


@router.get(
    "/{net}/ajax_statistics/statistics_classified_pools_delegator_count/{width}",
    response_class=Response,
)
async def statistics_classified_pools_delegator_count(
    request: Request,
    net: str,
    width: int,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request)
    analysis = "statistics_classified_pools"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "user": user,
            },
        )

    all_data = get_all_data_for_analysis(analysis, mongodb)
    d_date = get_statistics_date(mongodb)
    df_pools = pd.DataFrame(all_data)
    df_pools = df_pools[
        [
            "date",
            "open_pool_count",
            "delegator_count",
            "delegator_avg_stake",
            "delegator_avg_count_per_pool",
        ]
    ]

    base = alt.Chart(df_pools).encode(alt.X("date:T", title=None))
    delegator_count = base.mark_area(
        line={"color": "#EE9B54"},
        color=alt.Gradient(
            gradient="linear",
            stops=[
                alt.GradientStop(color="white", offset=0),
                alt.GradientStop(color="#EE9B54", offset=1),
            ],
            x1=1,
            x2=1,
            y1=1,
            y2=0,
        ),
    ).encode(alt.Y("delegator_count:Q", title=None))
    chart = delegator_count.properties(
        width="container",
        # width = 400,
        height=150,
        title={
            "text": "# Delegators",
            "subtitle": f"{d_date}",
        },
    )
    return chart.to_json(format="vega")


@router.get(
    "/{net}/ajax_statistics/statistics_classified_pools_avg_count_per_pool/{width}",
    response_class=Response,
)
async def statistics_classified_pools_avg_count_per_pool(
    request: Request,
    net: str,
    width: int,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request)
    analysis = "statistics_classified_pools"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "user": user,
            },
        )

    all_data = get_all_data_for_analysis(analysis, mongodb)
    d_date = get_statistics_date(mongodb)
    df_pools = pd.DataFrame(all_data)
    df_pools = df_pools[
        [
            "date",
            "open_pool_count",
            "delegator_count",
            "delegator_avg_stake",
            "delegator_avg_count_per_pool",
        ]
    ]

    base = alt.Chart(df_pools).encode(alt.X("date:T", title=None))
    delegator_avg_count_per_pool = base.mark_area(
        line={"color": "#6E97F7"},
        color=alt.Gradient(
            gradient="linear",
            stops=[
                alt.GradientStop(color="white", offset=0),
                alt.GradientStop(color="#6E97F7", offset=1),
            ],
            x1=1,
            x2=1,
            y1=1,
            y2=0,
        ),
    ).encode(alt.Y("delegator_avg_count_per_pool:Q", title=None))
    chart = delegator_avg_count_per_pool.properties(
        width="container",
        # width = 400,
        height=150,
        title={
            "text": "Average # Delegators per Pool",
            "subtitle": f"{d_date}",
        },
    )
    return chart.to_json(format="vega")


@router.get(
    "/{net}/ajax_statistics/statistics_classified_pools_avg_stake/{width}",
    response_class=Response,
)
async def statistics_classified_pools_avg_stake(
    request: Request,
    net: str,
    width: int,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request)
    analysis = "statistics_classified_pools"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "user": user,
            },
        )

    all_data = get_all_data_for_analysis(analysis, mongodb)
    d_date = get_statistics_date(mongodb)
    df_pools = pd.DataFrame(all_data)
    df_pools = df_pools[
        [
            "date",
            "open_pool_count",
            "delegator_count",
            "delegator_avg_stake",
            "delegator_avg_count_per_pool",
        ]
    ]

    base = alt.Chart(df_pools).encode(alt.X("date:T", title=None))
    delegator_avg_stake = base.mark_area(
        line={"color": "#AE7CF7"},
        color=alt.Gradient(
            gradient="linear",
            stops=[
                alt.GradientStop(color="white", offset=0),
                alt.GradientStop(color="#AE7CF7", offset=1),
            ],
            x1=1,
            x2=1,
            y1=1,
            y2=0,
        ),
    ).encode(alt.Y("delegator_avg_stake:Q", title=None))
    chart = delegator_avg_stake.properties(
        width="container",
        # width = 400,
        height=150,
        title={
            "text": "Delegator's Average Stake",
            "subtitle": f"{d_date}",
        },
    )
    return chart.to_json(format="vega")


@router.get(
    "/{net}/ajax_statistics/statistics_microccd/{width}",
    response_class=Response,
)
async def statistics_microccd(
    request: Request,
    net: str,
    width: int,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request)
    analysis = "statistics_microccd"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "user": user,
            },
        )

    all_data = get_all_data_for_analysis(analysis, mongodb)
    d_date = get_statistics_date(mongodb)
    df_microCCD = pd.DataFrame(all_data)
    df_microCCD["GTU_numerator"] = df_microCCD["GTU_numerator"].astype(float)
    df_microCCD["GTU_denominator"] = df_microCCD["GTU_denominator"].astype(float)
    df_microCCD["NRG_denominator"] = df_microCCD["NRG_denominator"].astype(float)
    df_microCCD["NRG_numerator"] = df_microCCD["NRG_numerator"].astype(float)
    df_microCCD["Price_of_regular_transfer"] = (
        501
        / 1_000_000
        * df_microCCD["GTU_numerator"]
        / df_microCCD["GTU_denominator"]
        / (df_microCCD["NRG_denominator"] / df_microCCD["NRG_numerator"])
    )

    NRG = (
        alt.Chart(df_microCCD)
        .mark_line(color="#70B785", opacity=0.99)
        .encode(
            y=alt.Y(
                "Price_of_regular_transfer:Q",
                title="Cost for regular transfer (in CCD)",
                scale=alt.Scale(zero=False, type="log"),
            ),
            x=alt.X("date:T", title=None),
        )
    )

    chart = NRG.properties(
        width="container",
        # width=400,
        height=350,
        title={
            "text": "Fee stabilization - (log scale)",
            "subtitle": f"{d_date}",
        },
    )
    return chart.to_json(format="vega")


@router.get(
    "/{net}/ajax_statistics/statistics_validator_staking/{width}",
    response_class=Response,
)
async def statistics_validator_staking(
    request: Request,
    net: str,
    width: int,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request)
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "user": user,
            },
        )

    d_date = get_statistics_date(mongodb)
    result = [x for x in mongodb.mainnet[Collections.paydays_current_payday].find({})]
    active_validators = []
    for pool in result:
        pool_status = pool["pool_status"]
        current_payday_info = CCD_CurrentPaydayStatus(
            **pool_status["current_payday_info"]
        )
        active_validators.append(
            {
                "Validator ID": pool["baker_id"],
                "Effective Stake": (
                    current_payday_info.baker_equity_capital
                    + current_payday_info.delegated_capital
                )
                / 1_000_000,
                "Validator Stake": current_payday_info.baker_equity_capital / 1_000_000,
                "Delegated Stake": current_payday_info.delegated_capital / 1_000_000,
            }
        )

    df_bakers = pd.DataFrame(active_validators)
    df_bakers = (
        df_bakers.sort_values(by="Effective Stake", ascending=False)
        .head(50)
        .reset_index()
    )
    # df.reset_index(level=0, inplace=True)
    df_bakers = df_bakers.drop(["Effective Stake"], axis=1)
    df_bakers["o"] = df_bakers.index
    df_bakers["order"] = df_bakers["o"] + 1

    melt = df_bakers.melt(
        ["Validator ID", "order", "o", "index"],
        var_name="stakeType",
        value_name="value",
    )

    bar = (
        alt.Chart(melt)
        .mark_bar()
        .encode(
            y=alt.Y(
                "Validator ID:O", title=None, sort=alt.EncodingSortField(field="order")
            ),
            x=alt.X("value:Q", title="Staked Amount"),
            color=alt.Color(
                "stakeType",
                legend=alt.Legend(orient="bottom"),
                sort=alt.EncodingSortField("stakeType", order="descending"),
            ),
            order=alt.Order(
                # Sort the segments of the bars by this field
                "stakeType",
                sort="descending",
            ),
        )
    )

    chart = (bar).properties(
        width="container",
        # width=700,
        height=500,
        title={
            "text": "Validator (top 50) - Staked amounts",
            "subtitle": f"{d_date}",
        },
    )
    return chart.to_json(format="vega")


@router.get(
    "/{net}/ajax_statistics/statistics_ccd_on_exchanges/{width}",
    response_class=Response,
)
async def statistics_ccd_on_exchanges(
    request: Request,
    net: str,
    width: int,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request)
    analysis = "statistics_ccd_classified"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "user": user,
            },
        )

    all_data = get_all_data_for_analysis(analysis, mongodb)
    d_date = get_statistics_date(mongodb)
    source = pd.DataFrame(all_data)

    source = source[
        ["date", "bitfinex", "bitglobal", "mexc", "ascendex", "kucoin", "coinex"]
    ]
    islands = (source["bitfinex"] != 0).groupby(level=0).cumsum()
    source = source[islands != 0]
    source2 = source.copy()
    source2["date"] = (
        pd.to_datetime(source2["date"])
        + dt.timedelta(days=1)
        - dt.timedelta(microseconds=1)
    )

    melt = source2.melt("date", var_name="ccd_type", value_name="CCD")
    melt["ccd_type"] = melt["ccd_type"].replace(
        {
            "bitfinex": "1.BitFinex",
            "bitglobal": "2.BitGlobal",
            "mexc": "3.MEXC",
            "ascendex": "4.AscendEX",
            "kucoin": "5.KuCoin",
            "coinex": "6.CoinEx",
        }
    )

    rng = ["#DC5050", "#33C364", "#2485DF", "#7939BA", "#E87E90", "#F6DB9A"]
    columns = [
        "1.BitFinex",
        "2.BitGlobal",
        "3.MEXC",
        "4.AscendEX",
        "5.KuCoin",
        "6.CoinEx",
    ]

    # columns = [ 'BitFinex', 'BitGlobal', 'MEXC', 'AscendEX']
    area = (
        alt.Chart(melt)
        .mark_area(color="#AE7CF7", opacity=0.7)
        .encode(
            alt.X("date:T", title=None, axis=alt.Axis(grid=False)),
            y=alt.Y("CCD:Q", title="CCD on exchanges", sort=None),
            color=alt.Color(
                "ccd_type",
                title="Exchanges",
                scale=alt.Scale(domain=columns, range=rng),
            ),
        )
    )

    chart = (
        (area)  # + listings)
        .properties(
            width="container",
            # width=400,
            height=350,
            title={
                "text": "CCD on Exchanges",
                "subtitle": f"{d_date}",
            },
        )
        .configure_legend(
            orient="bottom",
            direction="vertical",
            fillColor="white",
            padding=5,
            strokeColor="gray",
            labelFontSize=9,
        )
    )

    return chart.to_json(format="vega")


@router.get(
    "/{net}/ajax_statistics/statistics_ccd_classified/{width}",
    response_class=Response,
)
async def statistics_ccd_classified(
    request: Request,
    net: str,
    width: int,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request)
    analysis = "statistics_ccd_classified"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "user": user,
            },
        )

    all_data = get_all_data_for_analysis(analysis, mongodb)
    d_date = get_statistics_date(mongodb)
    df_ccd_classified = pd.DataFrame(all_data)

    all_data = get_all_data_for_analysis("statistics_release_amounts", mongodb)
    df_release = pd.DataFrame(all_data)

    df_ccd_classified["tradable"] = (
        df_ccd_classified["bitfinex"]
        + df_ccd_classified["bitglobal"]
        + df_ccd_classified["mexc"]
        + df_ccd_classified["ascendex"]
        + df_ccd_classified["kucoin"]
        + df_ccd_classified["coinex"]
    )
    df_ccd_classified = df_ccd_classified[
        ["date", "staked", "delegated", "unstaked", "tradable"]
    ]
    melt = df_ccd_classified.melt("date", var_name="ccd_type", value_name="CCD")
    melt["order"] = melt["ccd_type"].replace(
        {
            val: i
            for i, val in enumerate(["staked", "delegated", "unstaked", "tradable"])
        }
    )
    df_ccd_classified = (
        df_ccd_classified.set_index("date")
        .join(df_release.set_index("date"))
        .reset_index()[["date", "total_amount_released", "total_amount"]]
    )
    df_ccd_classified["total_amount_released"] = df_ccd_classified[
        "total_amount_released"
    ].replace(np.nan, 0)
    df_ccd_classified["locked"] = (
        df_ccd_classified["total_amount"] - df_ccd_classified["total_amount_released"]
    ) / 1_000_000

    # rng = ["#AE7CF7", "#70B785", "#549FF2", "#EBBC90"]
    rng = ["#E87E90", "#33C364", "#2485DF", "#7939BA"]
    base = alt.Chart(
        melt,
    ).encode(x="date:T")
    columns = ["tradable", "unstaked", "staked", "delegated"]

    area = base.mark_area(opacity=1).encode(
        y="CCD:Q",
        color=alt.Color(
            "ccd_type",
            scale=alt.Scale(domain=columns, range=rng),
            sort=alt.EncodingSortField("order", order="descending"),
            legend=alt.Legend(title=None, titleAnchor="start", fillColor="white"),
        ),
        order="order",  # this controls stack order
    )

    chart = area.properties(
        # chart = alt.layer( area, line_locked ).properties(
        width="container",
        # width = 400,
        height=350,
        title={
            "text": "CCD Classified",
            "subtitle": f"{d_date}",
        },
    ).configure_legend(
        orient="bottom",
        direction="horizontal",
        fillColor="white",
        padding=5,
        strokeColor="gray",
        labelFontSize=9,
    )
    return chart.to_json(format="vega")


@router.get(
    "/{net}/ajax_statistics/statistics_network_activity/{width}",
    response_class=Response,
)
async def statistics_network_activity(
    request: Request,
    net: str,
    width: int,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request)
    analysis = "statistics_mongo_transactions"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "user": user,
            },
        )

    all_data = get_all_data_for_analysis(analysis, mongodb)
    d_date = get_statistics_date(mongodb)
    df_ccd_classified = pd.DataFrame(all_data)

    all_data = get_all_data_for_analysis("statistics_release_amounts", mongodb)
    df_release = pd.DataFrame(all_data)

    df_ccd_classified["tradable"] = (
        df_ccd_classified["bitfinex"]
        + df_ccd_classified["bitglobal"]
        + df_ccd_classified["mexc"]
        + df_ccd_classified["ascendex"]
        + df_ccd_classified["kucoin"]
        + df_ccd_classified["coinex"]
    )
    df_ccd_classified = df_ccd_classified[
        ["date", "staked", "delegated", "unstaked", "tradable"]
    ]
    melt = df_ccd_classified.melt("date", var_name="ccd_type", value_name="CCD")
    melt["order"] = melt["ccd_type"].replace(
        {
            val: i
            for i, val in enumerate(["staked", "delegated", "unstaked", "tradable"])
        }
    )
    df_ccd_classified = (
        df_ccd_classified.set_index("date")
        .join(df_release.set_index("date"))
        .reset_index()[["date", "total_amount_released", "total_amount"]]
    )
    df_ccd_classified["total_amount_released"] = df_ccd_classified[
        "total_amount_released"
    ].replace(np.nan, 0)
    df_ccd_classified["locked"] = (
        df_ccd_classified["total_amount"] - df_ccd_classified["total_amount_released"]
    ) / 1_000_000

    # rng = ["#AE7CF7", "#70B785", "#549FF2", "#EBBC90"]
    rng = ["#E87E90", "#33C364", "#2485DF", "#7939BA"]
    base = alt.Chart(
        melt,
    ).encode(x="date:T")
    columns = ["tradable", "unstaked", "staked", "delegated"]

    area = base.mark_area(opacity=1).encode(
        y="CCD:Q",
        color=alt.Color(
            "ccd_type",
            scale=alt.Scale(domain=columns, range=rng),
            sort=alt.EncodingSortField("order", order="descending"),
            legend=alt.Legend(title=None, titleAnchor="start", fillColor="white"),
        ),
        order="order",  # this controls stack order
    )

    chart = area.properties(
        # chart = alt.layer( area, line_locked ).properties(
        width="container",
        # width = 400,
        height=350,
        title={
            "text": "CCD Classified",
            "subtitle": f"{d_date}",
        },
    ).configure_legend(
        orient="bottom",
        direction="horizontal",
        fillColor="white",
        padding=5,
        strokeColor="gray",
        labelFontSize=9,
    )
    return chart.to_json(format="vega")


@router.get(
    "/{net}/ajax_statistics/statistics_network_activity_tps/{width}",
    response_class=Response,
)
async def statistics_network_activity_tps(
    request: Request,
    net: str,
    width: int,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request)
    analysis = "statistics_mongo_transactions"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "user": user,
            },
        )

    all_data = get_all_data_for_analysis(analysis, mongodb)
    d_date = get_statistics_date(mongodb)
    df_transactions = pd.DataFrame(all_data)

    all_data = get_all_data_for_analysis("statistics_network_activity", mongodb)
    df_day_activity = pd.DataFrame(all_data)

    merge = pd.merge(df_day_activity, df_transactions, on="date")
    merge["avgTransactionSize"] = (
        merge["network_activity"] / merge["account_transaction"]
    )
    # merge['transactionsPerBlock'] = merge['accountTransaction'] / merge['Mint']
    merge["TPS"] = merge["account_transaction"] / 86_400

    merge_tr = merge[merge["TPS"] > 0]
    merge_ac = merge[merge["network_activity"] > 0.0]
    tr = (
        alt.Chart(merge_tr)
        .mark_line(clip=True, color="#AE7CF7", opacity=1)
        .encode(
            y=alt.Y(
                "TPS:Q", title="Transactions Per Second (TPS)"
            ),  # , scale=alt.Scale(domain=[0,1])),
            x=alt.X("date:T", title=None),
        )
    )
    ac = (
        alt.Chart(merge_ac)
        .mark_area(
            line={"color": "#70B785"},
            color=alt.Gradient(
                gradient="linear",
                stops=[
                    alt.GradientStop(color="white", offset=0),
                    alt.GradientStop(color="#70B785", offset=1),
                ],
                x1=1,
                x2=1,
                y1=1,
                y2=0,
            ),
            opacity=0.75,
        )
        .encode(
            y=alt.Y(
                "network_activity:Q",
                title="CCD amounts transferred",
                scale=alt.Scale(zero=False, type="log"),
            ),
            x=alt.X("date:T", title=None),
        )
    )

    chart = (
        (ac + tr)
        .resolve_scale(y="independent")
        .properties(
            width="container",
            # width=400,
            height=350,
            title={
                "text": "Network Activity",
                "subtitle": f"{d_date}",
            },
        )
    )
    return chart.to_json(format="vega")


@router.get(
    "/{net}/ajax_statistics/statistics_transaction_details_histogram/{width}",
    response_class=Response,
)
async def statistics_transaction_details_histogram(
    request: Request,
    net: str,
    width: int,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request)
    analysis = "statistics_mongo_transactions"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "user": user,
            },
        )

    all_data = get_all_data_for_analysis(analysis, mongodb)
    d_date = get_statistics_date(mongodb)
    df = pd.DataFrame(all_data)

    df["account"] = df["initial"] + df["normal"] + df["credential_keys_updated"]
    df["staking"] = (
        df["baker_added"]
        + df["baker_removed"]
        + df["baker_keys_updated"]
        + df["baker_stake_updated"]
        # + df["baker_stake_earnings_updated"]
        + df["baker_configured"]
        + df["delegation_configured"]
    )
    df["smart ctr"] = (
        df["contract_initialized"]
        + df["module_deployed"]
        + df["contract_update_issued"]
    )
    df["register data"] = df["data_registered"]
    # df["chain updates"] = (
    #     df["micro_ccd_per_euro_update"]
    #     + df["euro_per_energy_update"]
    #     + df["pool_parameters_cpv_1_update"]
    #     + df["protocol_update"]
    #     + df["add_identity_provider_update"]
    #     + df["add_anonymity_revoker_update"]
    #     + df["level_1_update"]
    #     + df["time_parameters_cpv_1_update"]
    #     + df["mint_distribution_cpv_1_update"]
    #     + df["root_update"]
    #     + df["mint_distribution_update"]
    #     + df["baker_stake_threshold_update"]
    #     + df["gas_rewards_update"]
    #     + df["transaction_fee_distribution_update"]
    # )

    df["transfer"] = (
        df["account_transfer"]
        + df["transferred_to_encrypted"]
        + df["transferred_to_public"]
        + df["encrypted_amount_transferred"]
        + df["transferred_with_schedule"]
    )

    melt = df[
        [
            "date",
            "account",
            # "identity",
            "staking",
            # "delegation",
            "smart ctr",
            "transfer",
            "register data",
            # "chain updates",
        ]
    ].melt("date", var_name="transaction_type", value_name="count")

    rng = [
        "#EE9B54",
        "#F7D30A",
        "#6E97F7",
        "#F36F85",
        "#AE7CF7",
        "#508A86",
        "#005B58",
        # "#0E2625",
    ]
    # stacked hist
    norm_stack = (
        alt.Chart(melt)
        .mark_bar()
        .encode(
            x=alt.X("date:T"),  # , axis=None),
            y=alt.Y(
                "count",
                axis=alt.Axis(format="%"),
                title="% of daily txs",
                stack="normalize",
            ),
            color=alt.Color(
                "transaction_type", title="Transaction Type", scale=alt.Scale(range=rng)
            ),
        )
    )
    chart: Chart = (
        norm_stack.properties(
            width="container",
            # width = 400,
            height=350,
            title={
                "text": "Transaction Types",
                "subtitle": f"{d_date}",
            },
        )
        .configure_axis(grid=False)
        .configure_legend(
            orient="bottom",
            direction="vertical",
            fillColor="white",
            padding=5,
            strokeColor="gray",
            labelFontSize=9,
        )
    )

    return chart.to_json(format="vega")


@router.get(
    "/{net}/ajax_statistics/statistics_transaction_details_bubble/{width}",
    response_class=Response,
)
async def statistics_transaction_details_bubble(
    request: Request,
    net: str,
    width: int,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request)
    analysis = "statistics_mongo_transactions"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "user": user,
            },
        )

    all_data = get_all_data_for_analysis(analysis, mongodb)
    d_date = get_statistics_date(mongodb)
    df = pd.DataFrame(all_data)

    df["account"] = df["initial"] + df["normal"] + df["credential_keys_updated"]
    df["staking"] = (
        df["baker_added"]
        + df["baker_removed"]
        + df["baker_keys_updated"]
        + df["baker_stake_updated"]
        # + df["baker_stake_earnings_updated"]
        + df["baker_configured"]
        + df["delegation_configured"]
    )
    df["smart ctr"] = (
        df["contract_initialized"]
        + df["module_deployed"]
        + df["contract_update_issued"]
    )
    df["register data"] = df["data_registered"]
    # df["chain updates"] = (
    #     df["micro_ccd_per_euro_update"]
    #     + df["euro_per_energy_update"]
    #     + df["pool_parameters_cpv_1_update"]
    #     + df["protocol_update"]
    #     + df["add_identity_provider_update"]
    #     + df["add_anonymity_revoker_update"]
    #     + df["level_1_update"]
    #     + df["time_parameters_cpv_1_update"]
    #     + df["mint_distribution_cpv_1_update"]
    #     + df["root_update"]
    #     + df["mint_distribution_update"]
    #     + df["baker_stake_threshold_update"]
    #     + df["gas_rewards_update"]
    #     + df["transaction_fee_distribution_update"]
    # )

    df["transfer"] = (
        df["account_transfer"]
        + df["transferred_to_encrypted"]
        + df["transferred_to_public"]
        + df["encrypted_amount_transferred"]
        + df["transferred_with_schedule"]
    )

    melt = df[
        [
            "date",
            "account",
            # "identity",
            "staking",
            # "delegation",
            "smart ctr",
            "transfer",
            "register data",
            # "chain updates",
        ]
    ].melt("date", var_name="transaction_type", value_name="count")

    rng = [
        "#EE9B54",
        "#F7D30A",
        "#6E97F7",
        "#F36F85",
        "#AE7CF7",
        "#508A86",
        "#005B58",
        # "#0E2625",
    ]
    # bubble
    bubble = (
        alt.Chart(melt)
        .mark_circle()
        .encode(
            alt.X("date:T", bin=False),
            alt.Y("transaction_type:N", title=None, bin=False),
            size=alt.Size("count:Q", title="Count", bin=False),
            color=alt.Color(
                "transaction_type",
                title="Transaction Type",
                scale=alt.Scale(range=rng),
                legend=None,
            ),
        )
    )

    chart = (
        bubble.properties(
            width="container",
            # width = 400,
            height=200,
            # title={"text":None}
        )
        .configure_axis(grid=False)
        .configure_legend(
            orient="bottom",
            direction="horizontal",
            fillColor="white",
            padding=5,
            strokeColor="gray",
            labelFontSize=9,
        )
    )

    return chart.to_json(format="vega")


@router.get(
    "/{net}/ajax_statistics/statistics_exchange_wallets/{width}",
    response_class=Response,
)
async def statistics_exchange_wallets(
    request: Request,
    net: str,
    width: int,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request)
    analysis = "statistics_exchange_wallets"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "user": user,
            },
        )

    all_data = get_all_data_for_analysis(analysis, mongodb)
    d_date = get_statistics_date(mongodb)
    df = pd.DataFrame(all_data)
    melt = pd.DataFrame(df).melt(id_vars=["date"])

    base = alt.Chart(melt).encode(alt.X("date:T", axis=alt.Axis(title=None)))
    rng = [
        "#EE9B54",
        "#F7D30A",
        "#6E97F7",
        "#F36F85",
        "#AE7CF7",
        "#508A86",
        "#005B58",
        "#0E2625",
    ]

    line = base.mark_line().encode(
        y=alt.Y("value:Q", axis=alt.Axis(title="Count of Known Exchange Wallets")),
        tooltip=[
            alt.Tooltip("date:T", title="Date"),
            alt.Tooltip("value:Q", title="Count", format=",.0f"),
            alt.Tooltip("variable:O", title="Exchange"),
        ],
        color=alt.Color(
            "variable:O",
            scale=alt.Scale(range=rng),
            # sort=alt.EncodingSortField("order", order="descending"),
            legend=alt.Legend(
                title=None,
                titleAnchor="start",
                fillColor="white",
                orient="bottom",
                columns=2,
            ),
        ),
    )
    chart = line.properties(
        width="container",
        # width=400,
        height=350,
        title={
            "text": "Known Exchange Wallets",
            "subtitle": f"{d_date}",
        },
    )
    return chart.to_json(format="vega")


@router.get(
    "/{net}/ajax_statistics/statistics_transaction_fees/{width}",
    response_class=Response,
)
async def statistics_transaction_fees(
    request: Request,
    net: str,
    width: int,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request)
    analysis = "statistics_transaction_fees"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "user": user,
            },
        )

    all_data = get_all_data_for_analysis(analysis, mongodb)
    d_date = get_statistics_date(mongodb)
    df = pd.DataFrame(all_data)
    df.fillna(0)
    df["fee_for_day"] = df["fee_for_day"] / 1_000_000

    base = (
        alt.Chart(df)
        .mark_line(color="#EE9B54", opacity=0.99)
        .encode(
            y=alt.Y(
                "fee_for_day:Q",
                title="Transaction Fees (in CCD)",
                # scale=alt.Scale(zero=False, type="log"),
            ),
            x=alt.X("date:T", title=None),
            tooltip=[
                alt.Tooltip("date:T", title="Date"),
                alt.Tooltip(
                    "fee_for_day:Q", title="Transaction Fees (CCD)", format=",.0f"
                ),
            ],
        )
    )

    chart = base.properties(
        width="container",
        # width=400,
        height=350,
        title={
            "text": "Transaction Fees per Day",
            "subtitle": f"{d_date}",
        },
    )
    return chart.to_json(format="vega")


def dates_to_blocks(
    start_date: str, end_date: str, blocks_per_day: dict[str, MongoTypeBlockPerDay]
):
    amended_start_date = (
        f"{(dateutil.parser.parse(start_date)-dt.timedelta(days=1)):%Y-%m-%d}"
    )
    start_block = blocks_per_day.get(amended_start_date)
    if start_block:
        start_block = start_block.height_for_first_block
    else:
        start_block = 0

    end_block = blocks_per_day.get(end_date)
    if end_block:
        end_block = end_block.height_for_last_block
    else:
        end_block = 1_000_000_000

    return start_block, end_block


@router.get(
    "/ajax_transaction_fees_graph/{start_date}/{end_date}/{period}/{type}/{width}",
    response_class=JSONResponse,
)
async def statistics_transaction_fees_ajax(
    request: Request,
    start_date: str,
    end_date: str,
    period: str,
    type: str,
    width: int,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    tooter: Tooter = Depends(get_tooter),
    # contracts_with_tag_info: dict = Depends(get_contracts_with_tag_info),
    token_addresses_with_markup: dict = Depends(get_token_addresses_with_markup),
    exchange_rates: dict = Depends(get_historical_rates),
    blocks_per_day: dict[str, MongoTypeBlockPerDay] = Depends(get_blocks_per_day),
):
    # user: UserV2 = get_user_detailsv2(request)
    net = "mainnet"

    try:
        statistics_transaction_fees_last_time = (
            request.app.statistics_transaction_fees_last_time
        )
    except AttributeError:
        statistics_transaction_fees_last_time = dt.datetime.now().astimezone(
            dt.timezone.utc
        )
    try:
        all_data = request.app.fees_all_data
    except AttributeError:
        all_data = None

    if (
        dt.datetime.now().astimezone(dt.timezone.utc)
        - statistics_transaction_fees_last_time
    ).total_seconds() < 3 and all_data:

        all_data = request.app.fees_all_data
    else:
        dates_to_include = generate_dates_from_start_until_end(start_date, end_date)
        all_data = get_all_data_for_analysis_limited(
            "statistics_transaction_fees", mongodb, dates_to_include
        )
        request.app_fees_all_data = all_data
        df = pd.DataFrame(all_data)

        if len(df) > 0:
            df["date"] = pd.to_datetime(df["date"])
            df["fee_for_day"] = df["fee_for_day"] / 1_000_000
            if period == "Daily":
                letter = "D"
                tooltip = "Day"
            if period == "Weekly":
                letter = "W"
                tooltip = "Week"
            if period == "Monthly":
                letter = "ME"
                tooltip = "Month"

            df_group = (
                df.groupby([pd.Grouper(key="date", axis=0, freq=letter)])
                .sum()
                .reset_index()
            )
            df_group.sort_values(by="date", ascending=False, inplace=True)

            if type == "graph":
                melt = pd.melt(
                    df_group,
                    id_vars=["date"],
                    value_vars=["fee_for_day"],
                )

                base = alt.Chart(melt)

                bar = base.mark_bar(
                    cornerRadiusTopLeft=3,
                    cornerRadiusTopRight=3,
                    size=15 if width < 400 else 15,
                ).encode(
                    alt.X("date:T", scale=alt.Scale(nice=True)),
                    y=alt.Y(
                        "value:Q",
                        title="Transaction Fees (CCD)",
                        scale=alt.Scale(nice=True),
                        axis=alt.Axis(
                            grid=False,
                            #    offset=10,
                            format=".2s",
                        ),
                    ),
                    # color=alt.Color(
                    #     "variable:N", title="Reward Type", scale=alt.Scale(range=rng)
                    # ),
                    tooltip=[
                        alt.Tooltip("date:T", title=f"{tooltip} Ending"),
                        alt.Tooltip(
                            "value:Q", title="Transaction Fees (CCD)", format=",.0f"
                        ),
                    ],
                )
                chart = bar.properties(
                    # width='container',
                    width=width * 0.80 if width < 400 else width,
                    height=200,
                    title={
                        "text": f"Transaction Fees {period}",
                        # "subtitle": f"Account {account_index}",
                    },
                ).configure_legend(
                    orient="bottom",
                    direction="horizontal",
                    fillColor="white",
                    padding=15,
                    labelPadding=15,
                    strokeColor="gray",
                    labelFontSize=9,
                )

                return Response(chart.to_json(format="vega"))
            else:

                return df_group.to_dict("records")
