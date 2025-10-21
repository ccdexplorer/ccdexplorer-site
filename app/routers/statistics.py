# ruff: noqa: F403, F405, E402, E501, E722, F401

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from app.classes.dressingroom import TransactionClassifier

# from app.classes.Node_Baker import BakerStatus
from app.jinja2_helpers import *

# from app.ajax_helpers import mongo_pagination_html_header
from app.env import *
from app.state import *
from app.routers.tools import get_data_for_chain_transactions_for_dates
import requests
from typing import Optional, Union
import numpy as np
from bisect import bisect_right
from app.utils import user_string
from pydantic import ConfigDict
from ccdexplorer_fundamentals.user_v2 import UserV2, NotificationPreferences

# from app.Recurring.recurring import Recurring
from ccdexplorer_fundamentals.cis import MongoTypeLoggedEvent
from pymongo import ASCENDING, DESCENDING
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_PoolInfo,
    CCD_CurrentPaydayStatus,
    CCD_BlockItemSummary,
)
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import uuid


router = APIRouter()


def prepare_plotly_graph(data: list, title: str, d_date: str, layout_additions: dict):
    return_object = {
        "layout": {
            "title": {
                "text": f"<b>{title}</b><br><sup>{d_date}</sup>",
                "font": {"size": 14},
            },
            # "plot_bgcolor": "#444",
            "paper_bgcolor": "rgba(0,0,0,0)",
            "xaxis": {"linecolor": "grey", "linewidth": 1, "mirror": True},
            "yaxis": {"linecolor": "grey", "linewidth": 1, "mirror": True},
            "legend": {"x": 0.01, "y": 0.99, "xanchor": "left", "yanchor": "top"},
        },
        "data": data,
        "config": {"responsive": True, "displayModeBar": False},
    }
    return_object["layout"].update(layout_additions)
    return return_object


def get_txs_for_impacted_address_cdex(app):
    result = mongodb.mainnet_db["impacted_addresses"].find(
        {"impacted_address_canonical": "<9363,0>"}, projection={"_id": 0, "tx_hash": 1}
    )
    return [x["tx_hash"] for x in list(result)]


def get_txs_for_impacted_address_arabella(app):
    result = mongodb.mainnet_db["impacted_addresses"].find(
        {"impacted_address_canonical": "<9337,0>"}, projection={"_id": 0, "tx_hash": 1}
    )
    return [x["tx_hash"] for x in list(result)]


def get_txs_for_impacted_address_tricorn(app):
    pipeline = [
        {"$match": {"impacted_address_canonical": "<9427,0>"}},
        {"$project": {"_id": 0, "tx_hash": 1}},
    ]

    result = mongodb.mainnet[Collections.impacted_addresses].aggregate(pipeline)
    bridge_txs = set(x["tx_hash"] for x in result)

    pipeline = [
        {
            "$match": {
                "impacted_address_canonical": {
                    "$in": ["<9428,0>", "<9429,0>", "<9430,0>"],
                },
            }
        },
        {"$project": {"_id": 0, "tx_hash": 1}},
    ]

    result = mongodb.mainnet[Collections.impacted_addresses].aggregate(pipeline)
    wrong_txs = set(x["tx_hash"] for x in result)
    return list(bridge_txs - wrong_txs)

    # result = mongodb.mainnet_db["impacted_addresses"].find(
    #     {"impacted_address_canonical": "<9427,0>"}, projection={"_id": 0, "tx_hash": 1}
    # )
    # return [x["tx_hash"] for x in list(result)]


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
    Tricorn = "Tricorn"


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

        elif reporting_subject == ReportingSubject.Tricorn:

            if classified_tx.logged_events[0].event_type == "mint_event":
                classified_tx.action_type = ReportingActionType.mint
            # Tricorn burn txs seem to have a fee transfer as first logged event,
            # hence we need to take the second logged event to classify correctly.
            if len(classified_tx.logged_events) > 1:
                if classified_tx.logged_events[1].event_type == "burn_event":
                    classified_tx.action_type = ReportingActionType.burn

        txs_by_action_type[classified_tx.action_type].append(classified_tx)
    return txs_by_action_type, tx_hashes_from_events


def get_analytics_for_platform(
    reporting_subject: ReportingSubject,
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
        elif reporting_subject == ReportingSubject.Tricorn:
            tx_hashes = get_txs_for_impacted_address_tricorn(mongodb)

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
):
    if net == "mainnet":

        return templates.TemplateResponse(
            "statistics/statistics-chain.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )
    else:
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )


@router.get("/{net}/statistics/accounts", response_class=HTMLResponse)
async def statistics_accounts(
    request: Request,
    net: str,
):
    if net == "mainnet":

        return templates.TemplateResponse(
            "statistics/statistics-chain-accounts.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )
    else:
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )


@router.get("/{net}/statistics/chain", response_class=HTMLResponse)
async def statistics_chain(
    request: Request,
    net: str,
):
    if net == "mainnet":

        return templates.TemplateResponse(
            "statistics/statistics-chain-chain.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )
    else:
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )


@router.get("/{net}/statistics/exchanges", response_class=HTMLResponse)
async def statistics_exchanges(
    request: Request,
    net: str,
):
    if net == "mainnet":

        return templates.TemplateResponse(
            "statistics/statistics-chain-exchanges.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )
    else:
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )


@router.get("/{net}/statistics/staking", response_class=HTMLResponse)
async def statistics_staking(
    request: Request,
    net: str,
):
    if net == "mainnet":

        return templates.TemplateResponse(
            "statistics/statistics-chain-staking.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )
    else:
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )


@router.get("/{net}/statistics/validators", response_class=HTMLResponse)
async def statistics_validators(
    request: Request,
    net: str,
):
    if net == "mainnet":

        return templates.TemplateResponse(
            "statistics/statistics-chain-validators.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )
    else:
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )


@router.get("/{net}/statistics/plt", response_class=HTMLResponse)
async def statistics_plt(
    request: Request,
    net: str,
):
    if net == "mainnet":

        return templates.TemplateResponse(
            "statistics/statistics-chain-plt.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )
    else:
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )


@router.get("/{net}/statistics-standalone", response_class=HTMLResponse)
async def statistics_standalone(
    request: Request,
    net: str,
):
    if net == "mainnet":
        chain_start = dt.date(2021, 6, 9).strftime("%Y-%m-%d")
        yesterday = (
            dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)
        ).strftime("%Y-%m-%d")
        return templates.TemplateResponse(
            "statistics/standalone/account_growth.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "chain_start": chain_start,
                "yesterday": yesterday,
            },
        )
    else:
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
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
):
    # theme = await get_theme_from_request(request)

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
                    if action_type["action_type"] == "Burn":
                        tvl -= action_type["amount_in_usd"]

                if reporting_subject == ReportingSubject.Tricorn:
                    if action_type["action_type"] == "Mint":
                        tvl += action_type["amount_in_usd"]
                    if action_type["action_type"] == "Burn":
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
    "/ajax_events_tx_and_logged/{net}/statistics/{rep_subject}/{year_month}",
    response_class=Response,
)
async def statistics_ajax_reporting_subject_events_tx_logged_events(
    request: Request,
    net: str,
    rep_subject: str,
    year_month: str,
    # contracts_with_tag_info: dict = Depends(get_contracts_with_tag_info),
    # token_addresses_with_markup_both_nets: dict = Depends(
    #     get_token_addresses_with_markup
    # ),
    exchange_rates: dict = Depends(get_historical_rates),
):
    token_addresses_with_markup = token_addresses_with_markup_both_nets[NET.MAINNET]
    all_data = get_all_data_for_bridges_and_dexes_for_month(
        "statistics_bridges_and_dexes", rep_subject, year_month, mongodb
    )
    all_data = [x for x in all_data if len(x["action_types_for_day"]) > 0]

    all_logged_event_ids = {}
    all_tx_ids = {}
    for row in all_data:
        hashes = row["hashes_per_day"]
        for tx_object in hashes:
            all_tx_ids[tx_object["tx_hash"]] = len(tx_object["logged_events"])
            for event in tx_object["logged_events"]:
                all_logged_event_ids[event] = True

    # get tx
    pipeline = [{"$match": {"_id": {"$in": list(all_tx_ids.keys())}}}]
    tx_cache = {
        x["_id"]: CCD_BlockItemSummary(**x)
        for x in mongodb.mainnet[Collections.transactions].aggregate(pipeline)
    }

    # get logged_events
    pipeline = [{"$match": {"_id": {"$in": list(all_logged_event_ids.keys())}}}]
    logged_event_cache = {
        x["_id"]: MongoTypeLoggedEvent(**x)
        for x in mongodb.mainnet[Collections.tokens_logged_events].aggregate(pipeline)
    }
    html = ""
    html += templates.get_template(
        "statistics/statistics-tx-and-logged-events.html"
    ).render(
        {
            "net": net,
            "all_data": sorted(all_data, key=lambda x: x["date"], reverse=True),
            "tx_cache": tx_cache,
            "logged_event_cache": logged_event_cache,
            "token_addresses_with_markup": token_addresses_with_markup,
        }
    )
    return html


@router.get("/{net}/statistics/{reporting_subject}", response_class=HTMLResponse)
async def statistics_reporting_subject(
    request: Request,
    net: str,
    reporting_subject: str,
):
    error = "Not implemented yet."
    return templates.TemplateResponse(
        "base/error.html",
        {
            "request": request,
            "error": error,
            "env": environment,
            "net": net,
        },
    )
    # pipeline = [
    #     {"$match": {"type": "statistics_bridges_and_dexes"}},
    #     {"$match": {"reporting_subject": reporting_subject}},
    #     {"$match": {"action_types_for_day": {"$exists": True, "$not": {"$size": 0}}}},
    #     {
    #         "$project": {
    #             "yearMonth": {
    #                 "$dateToString": {
    #                     "format": "%Y-%m",
    #                     "date": {"$dateFromString": {"dateString": "$date"}},
    #                 }
    #             }
    #         }
    #     },
    #     {"$group": {"_id": "$yearMonth"}},
    #     {"$sort": {"_id": -1}},  # Optional: Sort the results by year-month
    # ]

    # # Execute the aggregation pipeline
    # results = mongodb.mainnet[Collections.statistics].aggregate(pipeline)

    # # Extract and print the unique YYYY-MM dates
    # year_months = [result["_id"] for result in results]
    # theme = await get_theme_from_request(request)
    # if net != "mainnet":
    #     return templates.TemplateResponse(
    #         "testnet/not-available.html",
    #         {
    #             "env": request.app.env,
    #             "net": net,
    #             "request": request,
    #             "user": user,
    #         },
    #     )
    # print(f"{net=}")
    # return templates.TemplateResponse(
    #     "statistics/statistics-bridge-dex-v2.html",
    #     {
    #         "env": request.app.env,
    #         "net": net,
    #         "request": request,
    #         "user": user,
    #         "year_months": year_months,
    #         "reporting_subject": reporting_subject,
    #     },
    # )


class AnalysisType(Enum):
    statistics_daily_holders = "statistics_daily_holders"
    statistics_daily_limits = "statistics_daily_limits"
    statistics_network_summary = "statistics_network_summary"
    statistics_classified_pools = "statistics_classified_pools"


def get_all_data_for_analysis(analysis: str, app) -> list[str]:
    return [
        x
        for x in mongodb.mainnet[Collections.statistics]
        .find({"type": analysis}, {"_id": 0, "type": 0})
        .sort("date", ASCENDING)
    ]


def get_all_data_for_analysis_for_token(
    analysis: str, token_address: str, app
) -> list[str]:
    return [
        x
        for x in mongodb.mainnet[Collections.statistics]
        .find(
            {"$and": [{"type": analysis}, {"token_address": token_address}]},
            {"_id": 0, "type": 0, "token_address": 0},
        )
        .sort("date", ASCENDING)
    ]


def get_all_data_for_bridges_and_dexes(
    analysis: str, reporting_subject: str, app
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


def get_all_data_for_bridges_and_dexes_for_month(
    analysis: str, reporting_subject: str, month_str: str, app
) -> list[str]:
    pipeline = [
        {"$match": {"type": analysis}},
        {"$match": {"date": {"$regex": f"{month_str}"}}},
        {"$match": {"reporting_subject": reporting_subject}},
        {
            "$project": {
                "_id": 0,
                "type": 0,
                "reporting_subject": 0,
            }
        },
        {"$sort": {"date": -1}},
    ]
    return list(mongodb.mainnet[Collections.statistics].aggregate(pipeline))


async def get_all_data_for_analysis_limited(
    analysis: str, app, start_date: str | dt.date, end_date: str
) -> list[str]:
    api_result = await get_url_from_api(
        f"{app.api_url}/v2/mainnet/misc/statistics/{analysis}/{start_date}/{end_date}",
        app.httpx_client,
    )
    result = api_result.return_value if api_result.ok else []
    return result


@router.post(
    "/{net}/ajax_statistics_plotly_py/statistics_daily_holders",
    response_class=HTMLResponse,
)
async def statistics_daily_holders_plotly(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    analysis = "statistics_daily_holders"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    chain_start = dt.date(2021, 6, 9)
    yesterday = (dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    all_data = await get_all_data_for_analysis_limited(
        analysis, request.app, chain_start, yesterday
    )
    d_date = yesterday
    df = pd.DataFrame(all_data)
    title = "Count of Accounts holding > 1M CCD"
    fig = px.bar(
        df,
        x="date",
        y="count_above_1M",
        template=ccdexplorer_plotly_template(theme),
    )
    fig.update_traces(marker_color="#549FF2")
    fig.update_yaxes(
        secondary_y=False,
        title_text=title,
        showgrid=False,
        title_font=dict(color="#549FF2"),
    )
    fig.update_layout(
        legend_title_text=None,
        title=f"<b>{title}</b><br><sup>{d_date}</sup>",
        height=350,
    )
    fig.update_xaxes(title=None)
    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )


@router.post(
    "/{net}/ajax_statistics_plotly_py/statistics_daily_limits",
    response_class=HTMLResponse,
)
async def statistics_daily_limits_plotly(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    analysis = "statistics_daily_limits"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    chain_start = dt.date(2021, 6, 9)
    yesterday = (dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    all_data = await get_all_data_for_analysis_limited(
        analysis, request.app, chain_start, yesterday
    )
    d_date = yesterday
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

    rng = ["#AE7CF7", "#70B785"]

    title = "Amounts of CCD needed to make top 100/250"
    fig = px.line(
        melt,
        x="date",
        y="value",
        color="limit_amount",
        color_discrete_sequence=rng,
        template=ccdexplorer_plotly_template(theme),
    )
    fig.update_yaxes(
        secondary_y=False,
        title_text="Amount (CCD)",
        showgrid=False,
        autorange=False,
    )
    fig.update_layout(
        legend=dict(
            orientation="h",
        ),
        legend_y=-0.2,
        yaxis_range=[0, round(max(df["Top 100"]), 0)],
        legend_title_text=None,
        title=f"<b>{title}</b><br><sup>{d_date}</sup>",
        height=350,
    )
    fig.update_xaxes(title=None)
    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )


@router.post(
    "/{net}/ajax_statistics_plotly_py/statistics_network_summary_validator_count",
    response_class=Response,
)
async def statistics_network_summary_validator_count_plotly(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    analysis = "statistics_network_summary"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    chain_start = dt.date(2021, 6, 9)
    yesterday = (dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    all_data = await get_all_data_for_analysis_limited(
        analysis, request.app, chain_start, yesterday
    )
    d_date = yesterday
    df = pd.DataFrame(all_data)
    df.fillna(0, inplace=True)
    df["active_validator_count"] = df["validator_count"] - df["suspended_count"]

    rng = ["#70B785"]
    title = "Registered Active and Suspended Validators"
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=df["date"].to_list(),
            y=df["active_validator_count"].to_list(),
            name="Active Validators",
            marker=dict(color="#70B785"),
        ),
        secondary_y=False,
    )
    # fig = px.line(
    #     df,
    #     x="date",
    #     y="active_validator_count",
    #     color_discrete_sequence=rng,
    #     template=ccdexplorer_plotly_template(theme),
    # )
    fig.add_trace(
        go.Bar(
            x=df["date"].to_list(),
            y=df["suspended_count"].to_list(),
            name="Suspended Validators",
            marker=dict(color="#AE7CF7"),
        ),
        secondary_y=False,
    )

    fig.update_yaxes(title_text="Validators")
    fig.update_xaxes(title=None)
    fig.update_layout(
        template=ccdexplorer_plotly_template(theme),
        legend_title_text=None,
        legend_y=-0.25,
        title=f"<b>{title}</b><br><sup>{d_date}</sup>",
        height=500,
    )
    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )


@router.post(
    "/{net}/ajax_statistics_plotly_py/statistics_network_summary_accounts_per_day",
    response_class=Response,
)
async def statistics_network_summary_accounts_per_day_plotly(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    analysis = "statistics_network_summary"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    chain_start = dt.date(2021, 6, 9)
    yesterday = (dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    all_data = await get_all_data_for_analysis_limited(
        analysis, request.app, chain_start, yesterday
    )
    d_date = yesterday
    df_per_day = pd.DataFrame(all_data)
    df_per_day["d_count_accounts"] = df_per_day["account_count"] - df_per_day[
        "account_count"
    ].shift(+1)

    df_per_day = df_per_day.dropna(subset=["d_count_accounts"])

    df_per_day.rename(
        columns={"d_count_accounts": "growth", "account_count": "level"}, inplace=True
    )
    df_per_day = df_per_day[["date", "growth", "level"]]
    title = "Accounts Active and Growth per day"

    # Create figure with secondary y-axis
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=df_per_day["date"].to_list(),
            y=df_per_day["level"].to_list(),
            name="Accounts On Chain",
            marker=dict(color="#AE7CF7"),
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Bar(
            x=df_per_day["date"].to_list(),
            y=df_per_day["growth"].to_list(),
            name="Account Growth",
            marker=dict(color="#549FF2"),
        ),
        secondary_y=True,
        # showgrid=False,
    )

    fig.update_yaxes(
        secondary_y=False,
        title_text="Accounts On Chain",
        showgrid=False,
        title_font=dict(color="#AE7CF7"),
    )
    fig.update_yaxes(
        secondary_y=True,
        title_text="Account Growth",
        showgrid=False,
        title_font=dict(color="#549FF2"),
    )
    fig.update_xaxes(type="date")
    fig.update_layout(
        showlegend=True,
        title=f"<b>{title}</b><br><sup>{d_date}</sup>",
        template=ccdexplorer_plotly_template(theme),
        height=350,
    )
    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )


@router.post(
    "/{net}/ajax_statistics_plotly_py/statistics_classified_pools_open_pool_count",
    response_class=Response,
)
async def statistics_classified_pools_open_pool_count_plotly(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    analysis = "statistics_classified_pools"
    title = "# Open Pools"
    plot_color = "#80B589"
    data_field = "open_pool_count"
    return await staking_graphs_plotly(
        analysis, request.app, title, plot_color, data_field, theme
    )


@router.post(
    "/{net}/ajax_statistics_plotly_py/statistics_classified_pools_delegator_count",
    response_class=Response,
)
async def statistics_classified_pools_delegator_count_plotly(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    analysis = "statistics_classified_pools"
    title = "# Delegators"
    plot_color = "#EE9B54"
    data_field = "delegator_count"
    return await staking_graphs_plotly(
        analysis, request.app, title, plot_color, data_field, theme
    )


@router.post(
    "/{net}/ajax_statistics_plotly_py/statistics_classified_pools_avg_count_per_pool",
    response_class=Response,
)
async def statistics_classified_pools_avg_count_per_pool_plotly(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    analysis = "statistics_classified_pools"
    title = "Average # Delegators per Pool"
    plot_color = "#6E97F7"
    data_field = "delegator_avg_count_per_pool"
    return await staking_graphs_plotly(
        analysis, request.app, title, plot_color, data_field, theme
    )


@router.post(
    "/{net}/ajax_statistics_plotly_py/statistics_classified_pools_avg_stake",
    response_class=Response,
)
async def statistics_classified_pools_avg_stake_plotly(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    analysis = "statistics_classified_pools"
    title = "Delegator's Average Stake"
    plot_color = "#AE7CF7"
    data_field = "delegator_avg_stake"
    return await staking_graphs_plotly(
        analysis, request.app, title, plot_color, data_field, theme
    )


async def staking_graphs_plotly(
    analysis, app, title, plot_color, data_field, theme: str
):
    chain_start = dt.date(2021, 6, 9)
    yesterday = (dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    all_data = await get_all_data_for_analysis_limited(
        analysis, app, chain_start, yesterday
    )
    d_date = yesterday
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
    rng = [plot_color]
    fig = px.area(
        df_pools,
        x="date",
        y=[data_field],
        color_discrete_sequence=rng,
        template=ccdexplorer_plotly_template(theme),
    )
    fig.update_yaxes(
        secondary_y=False,
        title_text=None,
        showgrid=False,
    )
    fig.update_xaxes(title_text=None)

    fig.update_layout(
        showlegend=False,
        title=f"<b>{title}</b><br><sup>{d_date}</sup>",
        height=275,
    )

    fig.update_traces(
        fillgradient=dict(
            type="vertical",
            colorscale=[(0.0, "white"), (1.0, plot_color)],
        ),
    )
    fig.add_trace(
        go.Scatter(
            x=df_pools["date"].to_list(),
            y=df_pools[data_field].to_list(),
            mode="lines",
            line=dict(color=plot_color, width=2),
            name=title,
        )
    )
    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )


@router.post(
    "/{net}/ajax_statistics_plotly_py/statistics_rewards_explained",
    response_class=Response,
)
async def statistics_rewards_explained(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )
    plot_color = "#AE7CF7"
    data_field = "restaked_rewards_perc"
    analysis = "statistics_daily_payday"
    title = "Distribution of Daily Rewards"
    staking_start = dt.date(2021, 6, 9)
    yesterday = (dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    all_data = await get_all_data_for_analysis_limited(
        analysis, request.app, staking_start, yesterday
    )
    d_date = yesterday
    df = pd.DataFrame(all_data)
    df = df[
        [
            "date",
            "total_rewards_validators",
            "total_rewards_pool_delegators",
            "total_rewards_passive_delegators",
        ]
    ]
    melt = df.melt("date", var_name="var", value_name="value")
    melt["var"] = melt["var"].replace(
        {
            "total_rewards_validators": "Validators",
            "total_rewards_pool_delegators": "Pool Delegators",
            "total_rewards_passive_delegators": "Passive Delegators",
        }
    )
    rng = ["#33C364", "#2485DF", "#7939BA", "#E87E90", "#F6DB9A", "#8BE7AA"]
    columns = ["Validators", "Pool Delegators", "Passive Delegators"]
    fig = px.area(
        melt,
        x="date",
        y="value",
        color="var",
        color_discrete_sequence=rng,
        category_orders={"var": columns},
        template=ccdexplorer_plotly_template(theme),
    )
    for trace in fig.data:
        trace.update(opacity=0.6)  # type: ignore
    fig.update_yaxes(
        secondary_y=False,
        title_text=None,
        showgrid=False,
        autorange=True,
    )
    fig.update_layout(
        legend=dict(
            orientation="h",
        ),
        # yaxis_range=[0, round(max(melt["CCD"]), 0)],
        xaxis_title=None,
        legend_title_text=None,
        legend_y=-0.25,  # -0.45,
        title=f"<b>{title}</b><br><sup>{d_date}</sup>",
        height=370,
    )
    # fig.update_traces(
    #     fillgradient=dict(
    #         type="vertical",
    #         colorscale=[(0.0, "white"), (1.0, plot_color)],
    #     ),
    # )
    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )


@router.post(
    "/{net}/ajax_statistics_plotly_py/statistics_restaked_rewards",
    response_class=Response,
)
async def statistics_restaked_rewards(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )
    plot_color = "#AE7CF7"
    data_field = "restaked_rewards_perc"
    analysis = "statistics_daily_payday"
    title = "Percentage of Daily Rewards Restaked"
    staking_start = dt.date(2022, 6, 24)
    yesterday = (dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    all_data = await get_all_data_for_analysis_limited(
        analysis, request.app, staking_start, yesterday
    )
    d_date = yesterday
    df = pd.DataFrame(all_data)
    df = df[["date", "restaked_rewards_perc"]]
    rng = [plot_color]
    fig = px.line(
        df,
        x="date",
        y=[data_field],
        color_discrete_sequence=rng,
        template=ccdexplorer_plotly_template(theme),
    )
    fig.update_yaxes(
        secondary_y=False,
        title_text=None,
        showgrid=False,
        tickformat=".0%",
        range=[0, 1],
    )
    fig.update_xaxes(title_text=None)

    fig.update_layout(
        showlegend=False,
        title=f"<b>{title}</b><br><sup>{d_date}</sup>",
        height=350,
    )

    # fig.update_traces(
    #     fillgradient=dict(
    #         type="vertical",
    #         colorscale=[(0.0, "white"), (1.0, plot_color)],
    #     ),
    # )

    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )


@router.post(
    "/{net}/ajax_statistics_plotly_py/statistics_microccd",
    response_class=Response,
)
async def statistics_microccd_plotly(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    analysis = "statistics_microccd"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    chain_start = dt.date(2021, 6, 9)
    yesterday = (dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    all_data = await get_all_data_for_analysis_limited(
        analysis, request.app, chain_start, yesterday
    )
    d_date = yesterday
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

    rng = ["#70B785"]
    title = "Fee stabilization - (log scale)"
    fig = px.line(
        df_microCCD,
        x="date",
        y="Price_of_regular_transfer",
        log_y=True,
        color_discrete_sequence=rng,
        template=ccdexplorer_plotly_template(theme),
    )
    fig.update_yaxes(title_text="Cost for regular transfer (in CCD)")
    fig.update_xaxes(title=None)
    fig.update_layout(
        legend_title_text=None,
        title=f"<b>{title}</b><br><sup>{d_date}</sup>",
        height=350,
    )
    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )


@router.post(
    "/{net}/ajax_statistics_plotly_py/statistics_validator_staking",
    response_class=Response,
)
async def statistics_validator_staking_plotly(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    yesterday = (dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    d_date = yesterday
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/mainnet/accounts/current-payday/info",
        request.app.httpx_client,
    )
    result = api_result.return_value if api_result.ok else []
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

    rng = ["#33C364", "#7939BA"]
    rng = ["#2485DF", "#E87E90"]
    title = "Validator (top 50) - Staked amounts"
    fig = px.bar(
        df_bakers,
        x=["Validator Stake", "Delegated Stake"],
        y="Validator ID",
        orientation="h",
        color_discrete_sequence=rng,
        template=ccdexplorer_plotly_template(theme),
    )
    fig.update_yaxes(
        type="category",
    )
    fig.update_xaxes(title="Staked Amount")
    fig.update_layout(
        legend_title_text=None,
        title=f"<b>{title}</b><br><sup>{d_date}</sup>",
        height=750,
        legend_y=0.0,
        legend_x=0.5,
        yaxis_dtick=1,
        uniformtext_minsize=8,
        uniformtext_mode="show",
        barmode="stack",
        yaxis={
            "categoryorder": "total ascending",
            "categoryarray": df_bakers["Validator ID"].to_list(),
        },
    )
    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )


@router.post(
    "/{net}/ajax_statistics_plotly_py/ccd_on_exchanges",
    response_class=HTMLResponse,
)
async def statistics_ccd_on_exchanges_plotly(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    analysis = "statistics_ccd_classified"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    chain_start = dt.date(2021, 6, 9)
    yesterday = (dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    all_data = await get_all_data_for_analysis_limited(
        analysis, request.app, chain_start, yesterday
    )
    d_date = yesterday
    source = pd.DataFrame(all_data)
    columns_to_be_removed = ["total_supply", "staked", "unstaked", "delegated"]
    columns_to_stay = list(set(source.columns) - set(columns_to_be_removed))
    source = source[columns_to_stay]
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
            "lcx": "7.LCX",
            "gate.io": "8.Gate.IO",
            "bitmart": "9.BitMart",
        }
    )

    rng = ["#DC5050", "#33C364", "#2485DF", "#7939BA", "#E87E90", "#F6DB9A", "#8BE7AA"]
    columns = [
        "1.BitFinex",
        "2.BitGlobal",
        "3.MEXC",
        "4.AscendEX",
        "5.KuCoin",
        "6.CoinEx",
        "7.LCX",
        "8.Gate.IO",
        "9.BitMart",
    ]

    title = "CCD on Exchanges"
    fig = px.area(
        melt,
        x="date",
        y="CCD",
        color="ccd_type",
        color_discrete_sequence=rng,
        category_orders={"ccd_type": columns},
        template=ccdexplorer_plotly_template(theme),
    )
    fig.update_yaxes(
        secondary_y=False,
        title_text="CCD on exchanges",
        showgrid=False,
        autorange=True,
    )
    fig.update_layout(
        legend=dict(
            orientation="h",
        ),
        # yaxis_range=[0, round(max(melt["CCD"]), 0)],
        xaxis_title=None,
        legend_title_text=None,
        legend_y=-0.25,  # -0.45,
        title=f"<b>{title}</b><br><sup>{d_date}</sup>",
        height=350,
    )
    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )


@router.post(
    "/{net}/ajax_statistics_plotly_py/statistics_ccd_classified",
    response_class=Response,
)
async def statistics_ccd_classified_plotly(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    analysis = "statistics_ccd_classified"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    chain_start = dt.date(2021, 6, 9)
    yesterday = (dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    all_data = await get_all_data_for_analysis_limited(
        analysis, request.app, chain_start, yesterday
    )
    all_data.reverse()
    d_date = yesterday
    df_ccd_classified = pd.DataFrame(all_data)

    all_data = await get_all_data_for_analysis_limited(
        "statistics_release_amounts", request.app, chain_start, yesterday
    )
    df_release = pd.DataFrame(all_data)

    cols = list(df_ccd_classified.columns)
    df_ccd_classified["gate.io"] = df_ccd_classified["gate.io"].fillna(0)
    df_ccd_classified["tradable"] = 0
    for col in [
        x
        for x in cols
        if x not in ["date", "total_supply", "staked", "unstaked", "delegated"]
    ]:
        df_ccd_classified["tradable"] += df_ccd_classified[col]
    # df_ccd_classified["bitfinex"]
    # + df_ccd_classified["bitglobal"]
    # + df_ccd_classified["mexc"]
    # + df_ccd_classified["ascendex"]
    # + df_ccd_classified["kucoin"]
    # + df_ccd_classified["coinex"]
    # + df_ccd_classified["lcx"]
    # )

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
    title = "CCD Classified"
    fig = px.bar(
        melt,
        x="date",
        y="CCD",
        color="ccd_type",
        color_discrete_sequence=rng,
        template=ccdexplorer_plotly_template(theme),
    )
    fig.update_layout(
        legend_title_text=None,
        title=f"<b>{title}</b><br><sup>{d_date}</sup>",
        height=350,
        legend_y=-0.1,
        legend_orientation="h",
    )
    fig.update_xaxes(title=None)
    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )



@router.post(
    "/{net}/ajax_statistics_plotly_py/percentage_staked",
    response_class=Response,
)
async def statistics_percentage_staked_plotly(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    analysis = "statistics_ccd_classified"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    chain_start = dt.date(2022, 6, 24)
    yesterday = (dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    all_data = await get_all_data_for_analysis_limited(
        analysis, request.app, chain_start, yesterday
    )
    all_data.reverse()
    d_date = yesterday
    
    all_data = await get_all_data_for_analysis_limited(
        analysis, request.app, chain_start, yesterday
    )
    df = pd.DataFrame(all_data)

    df["percentage_staked"] = (df["staked"] / df["total_supply"])*100
    
    

    rng = ["#E87E90", "#33C364", "#2485DF", "#7939BA"]
    title = "Percentage of CCD Staked"
    fig = px.bar(
        df,
        x="date",
        y="percentage_staked",
        color_discrete_sequence=rng,
        template=ccdexplorer_plotly_template(theme),
    )
    fig.update_layout(
        legend_title_text=None,
        title=f"<b>{title}</b><br><sup>{d_date}</sup>",
        height=350,
        yaxis=dict(type="linear", range=[0, 100], ticksuffix="%"),
        legend_y=-0.1,
        legend_orientation="h",
    )
    fig.update_xaxes(title=None)
    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )



@router.post(
    "/{net}/ajax_statistics_plotly_py/statistics_network_activity_tps",
    response_class=Response,
)
async def statistics_network_activity_tps_plotly(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    analysis = "statistics_mongo_transactions"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    chain_start = dt.date(2021, 6, 9)
    yesterday = (dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    all_data = await get_all_data_for_analysis_limited(
        analysis, request.app, chain_start, yesterday
    )
    d_date = yesterday
    df_transactions = pd.DataFrame(all_data)

    all_data = await get_all_data_for_analysis_limited(
        "statistics_network_activity", request.app, chain_start, yesterday
    )
    df_day_activity = pd.DataFrame(all_data)

    merge = pd.merge(df_day_activity, df_transactions, on="date")
    merge["avgTransactionSize"] = (
        merge["network_activity"] / merge["account_transaction"]
    )
    # merge['transactionsPerBlock'] = merge['accountTransaction'] / merge['Mint']
    merge["TPS"] = merge["account_transaction"] / 86_400

    merge_tr = merge[merge["TPS"] > 0]
    merge_ac = merge[merge["network_activity"] > 0.0]
    title = "Network Activity"

    # Create figure with secondary y-axis
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Scatter(
            x=merge_ac["date"].to_list(),
            y=merge_ac["network_activity"].to_list(),
            name="Activity",
            fill="tozeroy",
            marker=dict(color="#70B785"),
            fillgradient=dict(
                type="horizontal",
                colorscale=[(0.0, "white"), (1.0, "#70B785")],
            ),
        ),
        secondary_y=False,
        # showgrid=False,
    )
    fig.update_yaxes(secondary_y=False, type="log")
    # fig.update_traces(

    # )
    fig.add_trace(
        go.Scatter(
            x=merge_tr["date"].to_list(),
            y=merge_tr["TPS"].to_list(),
            name="TPS",
            marker=dict(color="#AE7CF7"),
        ),
        secondary_y=True,
    )
    fig.update_yaxes(
        secondary_y=False,
        title_text="Activity",
        showgrid=False,
        title_font=dict(color="#70B785"),
    )
    fig.update_yaxes(
        secondary_y=True,
        title_text="TPS",
        showgrid=False,
        title_font=dict(color="#AE7CF7"),
    )
    fig.update_xaxes(type="date")
    fig.update_layout(
        legend=dict(
            orientation="h",
        ),
        xaxis_title=None,
        showlegend=True,
        legend_y=-0.2,
        title=f"<b>{title}</b><br><sup>{d_date}</sup>",
        template=ccdexplorer_plotly_template(theme),
        height=350,
    )
    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )


@router.post(
    "/{net}/ajax_statistics_plotly_py/statistics_transaction_details_histogram",
    response_class=HTMLResponse,
)
async def statistics_transaction_details_histogram_python(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    analysis = "statistics_mongo_transactions"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    chain_start = dt.date(2021, 6, 9)
    yesterday = (dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    all_data = await get_all_data_for_analysis_limited(
        analysis, request.app, chain_start, yesterday
    )
    d_date = yesterday
    df = pd.DataFrame(all_data)
    df = df.fillna(0)
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
    title = "Transaction Types"
    fig = px.bar(
        melt,
        x="date",
        y="count",
        color="transaction_type",
        template=ccdexplorer_plotly_template(theme),
    )
    fig.update_layout(
        legend=dict(
            orientation="h",
        ),
        xaxis_title=None,
        legend_y=-0.2,
        legend_title_text=None,
        title=f"<b>{title}</b><br><sup>{d_date}</sup>",
        height=350,
    )
    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )


@router.post(
    "/{net}/ajax_statistics_plotly_py/statistics_exchange_wallets",
    response_class=Response,
)
async def statistics_exchange_wallets_plotly(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    analysis = "statistics_exchange_wallets"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    chain_start = dt.date(2021, 6, 9)
    yesterday = (dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    all_data = await get_all_data_for_analysis_limited(
        analysis, request.app, chain_start, yesterday
    )
    d_date = yesterday
    df = pd.DataFrame(all_data)
    melt = pd.DataFrame(df).melt(id_vars=["date"])

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

    title = "Known Exchange Wallets"
    fig = px.line(
        melt,
        x="date",
        y="value",
        color="variable",
        color_discrete_sequence=rng,
        template=ccdexplorer_plotly_template(theme),
    )
    fig.update_yaxes(
        title_text="Count",
        showgrid=False,
    )
    fig.update_layout(
        legend=dict(
            orientation="h",
        ),
        yaxis_range=[0, round(max(melt["value"]), 0) * 1.1],
        xaxis_title=None,
        legend_title_text=None,
        legend_y=-0.25,
        title=f"<b>{title}</b><br><sup>{d_date}</sup>",
        height=350,
    )
    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )


@router.post(
    "/{net}/ajax_statistics_plotly_py/statistics_transaction_fees",
    response_class=Response,
)
async def statistics_transaction_fees_plotly(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    analysis = "statistics_transaction_fees"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    chain_start = dt.date(2021, 6, 9)
    yesterday = (dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    all_data = await get_all_data_for_analysis_limited(
        analysis, request.app, chain_start, yesterday
    )
    d_date = yesterday
    df = pd.DataFrame(all_data)
    df.fillna(0)
    df["fee_for_day"] = df["fee_for_day"] / 1_000_000

    rng = ["#EE9B54"]
    title = "Transaction Fees per Day"
    fig = px.line(
        df,
        x="date",
        y="fee_for_day",
        color_discrete_sequence=rng,
        template=ccdexplorer_plotly_template(theme),
    )
    fig.update_yaxes(
        # secondary_y=False,
        title_text="Transaction Fees (CCD)",
        # showgrid=False,
        autorange=False,
    )
    fig.update_xaxes(title=None)
    fig.update_layout(
        yaxis_range=[0, round(max(df["fee_for_day"]), 0) * 1.1],
        legend_title_text=None,
        title=f"<b>{title}</b><br><sup>{d_date}</sup>",
        height=350,
    )
    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )


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


@router.post(
    "/ajax_transaction_fees_graph/{start_date}/{end_date}/{period}/{type}/{width}",
    # response_class=JSONResponse | HTMLResponse,
)
async def statistics_transaction_fees_ajax(
    request: Request,
    start_date: str,
    end_date: str,
    period: str,
    type: str,
    width: int,
):
    # theme = await get_theme_from_request(request)
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
        # dates_to_include = generate_dates_from_start_until_end(start_date, end_date)
        all_data = get_all_data_for_analysis_limited(
            "statistics_transaction_fees", request.app, start_date, end_date
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
                df_group["date"] = df_group["date"].dt.strftime("%Y-%m-%d")
                records = df_group.to_dict("records")
                filename = f"/tmp/transaction fees - {dt.datetime.now():%Y-%m-%d %H-%M-%S} grouped {period.lower()} - {uuid.uuid4()}.csv"
                df_group.columns = [f"{tooltip} Ending", "Sum of Fees (CCD)"]
                df_group.to_csv(filename, index=False)

                html = templates.get_template(
                    "/chain-information/transaction_fees_table.html"
                ).render(
                    {
                        "env": request.app.env,
                        "net": net,
                        "request": request,
                        "records": records,
                        "period": period,
                        "filename": filename,
                    },
                )
                return html


@router.post(
    "/{net}/ajax_statistics_plotly_py/statistics_unique_addresses",
    response_class=Response,
)
async def statistics_unique_addresses_plotly(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    analysis = "statistics_unique_addresses_weekly"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    chain_start = dt.date(2021, 6, 9)
    yesterday = (dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    all_data = await get_all_data_for_analysis_limited(
        analysis, request.app, chain_start, yesterday
    )
    d_date = yesterday
    df = pd.DataFrame(all_data)
    df.fillna(0)
    df["date"] = pd.to_datetime(df["date"])
    rng = ["#EE9B54"]
    title = "Unique Active Addresses per Week"
    fig = px.scatter(
        df,
        x="date",
        y="unique_impacted_address_count",
        color_discrete_sequence=rng,
        # mode="lines",
        template=ccdexplorer_plotly_template(theme),
        # trendline="rolling",
        # trendline_options=dict(window=12),
    )
    fig.update_yaxes(
        # secondary_y=False,
        title_text=None,
        # showgrid=False,
        # autorange=False,
    )
    fig.update_traces(mode="lines")
    fig.update_xaxes(title=None, type="date")

    fig.update_yaxes(secondary_y=False, type="log")
    fig.update_layout(
        # yaxis_range=[0, round(max(df["unique_impacted_address_count"]), 0) * 1.1],
        legend_title_text=None,
        title=f"<b>{title}</b><br><sup>{d_date}</sup>",
        height=350,
    )
    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )


########PLT


@router.post(
    "/{net}/ajax_statistics_plotly_py/statistics_plt_stablecoin_dominance",
    response_class=HTMLResponse,
)
async def statistics_plt_stablecoin_dominance_plotly(
    request: Request,
    net: str,
):
    theme = await get_theme_from_request(request)
    analysis = "statistics_plt"
    if net != "mainnet":
        return templates.TemplateResponse(
            "testnet/not-available.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
            },
        )

    chain_start = dt.date(2025, 9, 22)
    yesterday = (dt.datetime.now().astimezone(dt.UTC) - dt.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    all_data = await get_all_data_for_analysis_limited(
        analysis, request.app, chain_start, yesterday
    )
    d_date = yesterday
    df = pd.json_normalize(all_data)  # type: ignore
    x = df["date"]
    fig = go.Figure()
    usd_cols = [x for x in df.columns if ".USD.total_supply" in x]
    # rng = ["#33C364", "#2485DF", "#7939BA", "#E87E90", "#F6DB9A", "#8BE7AA"]
    rng = [
        "#33C364",  # green
        "#2485DF",  # blue
        "#7939BA",  # purple
        "#E87E90",  # red/pink
        "#F6DB9A",  # yellow
        "#8BE7AA",  # mint
        "#2EA856",  # green variant
        "#1F73C4",  # blue variant
        "#692F9F",  # purple variant
        "#D16475",  # red/pink variant
        "#EFCF7A",  # yellow variant
        "#71D895",  # mint variant
        "#52D98B",  # green
        "#4AA1EC",  # blue
        "#9559CC",  # purple
        "#EC9AA9",  # red/pink
        "#FAE4B5",  # yellow
        "#A3F0BE",  # mint
        "#1E7A3D",  # green
        "#155A91",  # blue
        "#4E1F75",  # purple
        "#A84352",  # red/pink
        "#D6B44F",  # yellow
        "#4EB872",  # mint
        "#6EE1A2",  # green
        "#7FBFF3",  # blue
        "#B27BD9",  # purple
        "#F2B8C2",  # red/pink
        "#FFF0CE",  # yellow
        "#C5F7D8",  # mint
    ]
    for index, col in enumerate(usd_cols):
        token = col.split(".")[1]

        fig.add_trace(
            go.Scatter(
                name=token,
                x=x,
                y=df[f"tokens.{token}.USD.total_supply"],
                mode="lines",
                # line=dict(width=0.5),
                stackgroup="one",
                marker=dict(color=rng[index]),
                groupnorm="percent",  # sets the normalization for the sum of the stackgroup
                hovertemplate=(
                    "date = %{x}"
                    "<br>TVL% in USD = %{y:.1f}%"
                    "<br>token = %{fullData.name}"
                    "<extra></extra>"
                ),
            )
        )
    title = "Stablecoin Dominance (TVL in USD)"

    fig.update_layout(
        showlegend=True,
        legend=dict(
            orientation="h",
        ),
        xaxis_type="category",
        yaxis=dict(type="linear", range=[1, 100], ticksuffix="%"),
    )

    fig.update_layout(
        template=ccdexplorer_plotly_template(theme),
        legend_title_text=None,
        title=f"<b>{title}</b><br><sup>{d_date}</sup>",
        height=350,
    )
    fig.update_xaxes(title=None)
    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )


#####################standalone
