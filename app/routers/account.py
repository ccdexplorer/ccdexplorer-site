# ruff: noqa: F403, F405, E402, E501, E722, F401
from __future__ import annotations

import copy
import json
import math
import altair as alt
import pandas as pd
from ccdexplorer_fundamentals.credential import Identity
from ccdexplorer_fundamentals.enums import NET
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import *
from ccdexplorer_fundamentals.mongodb import (
    AccountStatementEntry,
    AccountStatementEntryType,
    Collections,
    MongoDB,
    MongoImpactedAddress,
    MongoMotor,
    MongoTypeAccountReward,
)
from ccdexplorer_fundamentals.tooter import Tooter
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pymongo import ASCENDING, DESCENDING

# from rich import print
from app.ajax_helpers import (
    mongo_transactions_html_header,
    process_account_statement_to_HTML_v2,
    process_delegators_to_HTML_v2,
    process_tokens_to_HTML_v2,
    process_transactions_to_HTML,
    transactions_html_footer,
)
from app.classes.dressingroom import MakeUp, MakeUpRequest, TransactionClassifier
from app.classes.sankey import SanKey
from app.env import *
from app.jinja2_helpers import *
from app.Recurring.recurring import Recurring
from app.state.state import *
from app.utils import earliest

router = APIRouter()


def add_metadata_to_single_tokens(tokens_dict: dict, db_to_use, exchange_rates):
    # now add tag if found
    tokens_tags = {
        x["contracts"][0]: x
        for x in db_to_use[Collections.tokens_tags].find({"single_use_contract": True})
    }

    tokens_with_metadata = {}
    for contract, d in tokens_dict.items():
        if contract in tokens_tags.keys():
            # it's a single use contract
            d.update({"decimals": tokens_tags[contract]["decimals"]})
            d.update({"token_symbol": tokens_tags[contract]["get_price_from"]})
            d.update(
                {"token_value": int(d["token_amount"]) * (math.pow(10, -d["decimals"]))}
            )
            if d["token_symbol"] in exchange_rates:
                d.update(
                    {
                        "token_value_USD": d["token_value"]
                        * exchange_rates[d["token_symbol"]]["rate"]
                    }
                )
            else:
                d.update({"token_value_USD": 0})
            tokens_with_metadata[contract] = d

    tokens_value_USD = sum(
        [x["token_value_USD"] for x in tokens_with_metadata.values()]
    )
    return tokens_with_metadata, tokens_value_USD

    # for token_tag in tokens_tags:
    #     for contract in token_tag["contracts"]:
    #         tags_dict[contract] = {
    #             "tag": token_tag["_id"],
    #             "single_use_contract": token_tag["single_use_contract"],
    #         }
    #         if "hidden" in token_tag:
    #             tags_dict[contract].update({"hidden": token_tag["hidden"]})
    #         if "logo_url" in token_tag:
    #             tags_dict[contract].update({"logo_url": token_tag["logo_url"]})
    #         if "decimals" in token_tag:
    #             tags_dict[contract].update({"decimals": token_tag["decimals"]})

    # for token_address_str, item in tokens.items():
    #     if item["contract"] in tags_dict:
    #         item.update({"info": tags_dict[item["contract"]]})
    #         # if item["decimals"] in tags_dict:
    #         #     item.update({"decimals": tags_dict[item["decimals"]]})
    #         tokens[token_address_str] = item
    #         # if tags_dict[item["contract"]]["hidden"]:
    #         #     del tokens[token_address_str]
    #     else:
    #         metadata = retrieve_metadata_for_stored_token_address(
    #             token_address_str, db_to_use
    #         )
    #         if metadata:
    #             item.update({"info": metadata})
    #         else:
    #             item.update({"info": {"decimals": 0}})


def calc_apy_for_period(daily_apy: list) -> float:
    daily_ln = [math.log(1 + x) for x in daily_apy]
    avg_ln = sum(daily_ln) / len(daily_ln)
    expp = math.exp(avg_ln)
    apy = expp - 1
    return apy


def apy_for_baker_for_graph(mongodb: MongoDB, bakerId):
    query = {"_id": {"$eq": str(bakerId)}}
    # data = mongodb.mainnet[Collections.paydays_apy_intermediate].find(query)
    data = mongodb.mainnet[Collections.paydays_apy_intermediate].find(query)
    result = list(data)
    if len(result) > 0:
        result = result[0]
        daily_apy_dict = result["daily_apy_dict"]
        days_available = daily_apy_dict.keys()
        # days_available_last_date_first = sorted(days_available, reverse=True)

        daily_apy = []

        periods = [7, 30, 90, 180]

        calculated_results = []
        for day in days_available:
            # calculated_results[day] = {}
            if "baker" in daily_apy_dict[day]:
                baker_apy = daily_apy_dict[day]["baker"]["apy"]
                # reward = daily_apy_dict[day]["baker"]["reward"]
            else:
                baker_apy = 0
                # reward = 0

            if "delegator" in daily_apy_dict[day]:
                delegator_apy = daily_apy_dict[day]["delegator"]["apy"]
                # reward = daily_apy_dict[day]["delegator"]["reward"]
            else:
                delegator_apy = 0
                # reward = 0

            if "total" in daily_apy_dict[day]:
                total_apy = daily_apy_dict[day]["total"]["apy"]
                # reward = daily_apy_dict[day]["total"]["reward"]
            else:
                total_apy = 0
                # reward = 0
            daily_apy.append(
                {"baker": baker_apy, "delegator": delegator_apy, "total": total_apy}
            )
            # sum_rewards.append(reward)
            for period in periods:
                if len(daily_apy) >= period:
                    period_daily_apy: list[dict] = daily_apy[-period:]

                    apy_for_period_baker = calc_apy_for_period(
                        [x["baker"] for x in period_daily_apy]
                    )
                    apy_for_period_delegator = calc_apy_for_period(
                        [x["delegator"] for x in period_daily_apy]
                    )
                    apy_for_period_total = calc_apy_for_period(
                        [x["total"] for x in period_daily_apy]
                    )
                    calculated_results.append(
                        {
                            "date": day,
                            "period": period,
                            "baker": apy_for_period_baker,
                            "delegator": apy_for_period_delegator,
                            "total": apy_for_period_total,
                        }
                    )

        return calculated_results
    else:
        return None


def apy_for_baker(mongodb: MongoDB, bakerId):
    query = {"_id": {"$eq": str(bakerId)}}
    # data = mongodb.mainnet[Collections.paydays_apy_intermediate].find(query)
    data = mongodb.mainnet[Collections.paydays_apy_intermediate].find(query)
    result = list(data)
    if len(result) > 0:
        result = result[0]
        daily_apy_dict = result["daily_apy_dict"]
        days_available = daily_apy_dict.keys()
        days_available_last_date_first = sorted(days_available, reverse=True)

        calculated_results = {}
        periods = [7, 30, 90, 180]
        for period in periods:
            daily_apy = []
            sum_rewards = []

            if len(days_available_last_date_first) >= period:
                for day in days_available_last_date_first[:period]:
                    if "baker" in daily_apy_dict[day]:
                        apy = daily_apy_dict[day]["baker"]["apy"]
                        reward = daily_apy_dict[day]["baker"]["reward"]
                    else:
                        apy = 0
                        reward = 0
                    daily_apy.append(apy)
                    sum_rewards.append(reward)

                daily_ln = [math.log(1 + x) for x in daily_apy]
                avg_ln = sum(daily_ln) / len(daily_ln)
                expp = math.exp(avg_ln)
                apy = expp - 1
                calculated_results[period] = {"apy": apy, "rewards": sum(sum_rewards)}

                print(
                    f"baker APY {period}d: {(apy*100):,.2f}%, reward: {sum(sum_rewards):,.0f} CCD"
                )
            else:
                print(
                    f"Not enough data points to calc apy for {period}d. Only {len(days_available_last_date_first)} available."
                )


def calculate_baker_performance_measures(
    mongodb: MongoDB, baker_id, periods=[1, 7, 30]
):
    filter = {"bakerId": str(baker_id)}
    project = {"expectation": 1, "pool_status.currentPaydayStatus.blocksBaked": 1}
    sort = list({"date": -1}.items())

    result = list(
        mongodb.mainnet[Collections.paydays_performance].find(
            filter=filter, projection=project, sort=sort
        )
    )
    theo = [x["expectation"] for x in result]
    actual = [x["pool_status"]["currentPaydayStatus"]["blocksBaked"] for x in result]
    results = {}
    for period in periods:
        period_to_use = min(len(result), period)

        sum_theo = sum(theo[:period_to_use])
        sum_actual = sum(actual[:period_to_use])

        results[period] = sum_actual / sum_theo

    return results


async def get_txs_for_account_from_ia(
    account_id, start_block, end_block, mongomotor: MongoMotor
):
    pipeline = [
        {
            "$match": {"included_in_flow": True},
        },
        {"$match": {"block_height": {"$gt": start_block, "$lte": end_block}}},
        {
            "$match": {"impacted_address_canonical": {"$eq": account_id[:29]}},
        },
    ]
    txs_for_account = (
        await mongomotor.mainnet[Collections.impacted_addresses]
        .aggregate(pipeline)
        .to_list(1_000_000_000)
    )
    return txs_for_account


# async def get_get_account_rewards_pre_payday_sum_for_graph(
#     account_id: str, mongomotor: MongoMotor
# ):
#     pipeline = [
#         {
#             "$match": {"impacted_address_canonical": {"$eq": account_id[:29]}},
#         },
#         {"$match": {"effect_type": "Account Reward"}},
#         {
#             "$group": {
#                 "_id": "$impacted_address",
#                 "sum_finalization_reward": {
#                     "$sum": "$balance_movement.finalization_reward",
#                 },
#                 "sum_baker_reward": {
#                     "$sum": "$balance_movement.baker_reward",
#                 },
#                 "sum_transaction_fee_reward": {
#                     "$sum": "$balance_movement.transaction_fee_reward",
#                 },
#             },
#         },
#     ]

#     result = (
#         await mongomotor.mainnet[Collections.impacted_addresses_pre_payday]
#         .aggregate(pipeline)
#         .to_list(1_000_000_000)
#     )
#     return result


async def get_get_account_rewards_sum_for_graph(
    account_id, start_block, end_block, mongomotor: MongoMotor
):
    start_block = start_block if start_block > 3232445 else 3232445
    pipeline = [
        {
            "$match": {"impacted_address_canonical": {"$eq": account_id[:29]}},
        },
        {"$match": {"block_height": {"$gte": start_block, "$lte": end_block}}},
        {"$match": {"effect_type": "Account Reward"}},
        {
            "$group": {
                "_id": "$impacted_address",
                "sum_finalization_reward": {
                    "$sum": "$balance_movement.finalization_reward",
                },
                "sum_baker_reward": {
                    "$sum": "$balance_movement.baker_reward",
                },
                "sum_transaction_fee_reward": {
                    "$sum": "$balance_movement.transaction_fee_reward",
                },
            },
        },
    ]
    # result = list(mongodb.mainnet[Collections.impacted_addresses].aggregate(pipeline))
    result = (
        await mongomotor.mainnet[Collections.impacted_addresses]
        .aggregate(pipeline)
        .to_list(1_000_000_000)
    )
    return result


@router.get(
    "/ajax_sankey/{net}/{account_id}/{gte}/{start_date}/{end_date}",
    response_class=HTMLResponse,
)
async def request_sankey(
    request: Request,
    net: str,
    account_id: str,
    gte: str,
    start_date: str,
    end_date: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    recurring: Recurring = Depends(get_recurring),
    tags: dict = Depends(get_labeled_accounts),
    blocks_per_day: dict[str, MongoTypeBlockPerDay] = Depends(get_blocks_per_day),
    exchange_rates: dict = Depends(get_historical_rates),
):
    user: UserV2 = get_user_detailsv2(request)
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

    try:
        gte = int(gte.replace(",", "").replace(".", ""))
    except:
        error = True

    if net == "mainnet":
        # only transfer_in and transfer_out
        # console.log("1")
        txs_for_account = await get_txs_for_account_from_ia(
            account_id, start_block, end_block, mongomotor
        )
        # console.log("2")
        # only account rewards in payday era
        account_rewards = await get_get_account_rewards_sum_for_graph(
            account_id, start_block, end_block, mongomotor
        )
        # console.log("3")
        account_rewards_pre_payday = mongodb.mainnet[
            Collections.impacted_addresses_pre_payday
        ].find_one({"impacted_address_canonical": {"$eq": account_id[:29]}})
        # console.log("4")
        if account_rewards_pre_payday:
            account_rewards_total = account_rewards_pre_payday[
                "sum_transaction_fee_reward"
            ]
            +account_rewards_pre_payday["sum_baker_reward"]
            +account_rewards_pre_payday["sum_finalization_reward"]
            account_rewards[0]["sum_transaction_fee_reward"]
            +account_rewards[0]["sum_baker_reward"]
            +account_rewards[0]["sum_finalization_reward"]

        else:
            if len(account_rewards) > 0:
                account_rewards_total = (
                    account_rewards[0]["sum_transaction_fee_reward"]
                    + account_rewards[0]["sum_baker_reward"]
                    + account_rewards[0]["sum_finalization_reward"]
                )
            else:
                account_rewards_total = 0

        sankey = SanKey(account_id, gte, request.app)
        sankey.add_txs_for_account(
            txs_for_account, account_rewards_total, exchange_rates
        )
        sankey.cross_the_streams(user, tags)
        console.log("5")
        json_sankey = json.dumps(sankey.__dict__, skipkeys=True)
        return templates.TemplateResponse(
            "account/account_graph_table.html",
            {
                "env": request.app.env,
                "request": request,
                "user": user,
                "net": net,
                "account_id": account_id,
                "sankey": json_sankey,
                "graph_dict": sankey.graph_dict,
                "tags": tags,
            },
        )
    else:
        return "Not available on testnet."


async def get_blocks_per_payday(mongodb: MongoDB):
    result = {
        x["date"]: (x["height_for_last_block"] - x["height_for_first_block"] + 1)
        for x in mongodb.mainnet[Collections.paydays].find({})
    }
    return result


@router.get(
    # /mainnet/account/rewards-bucketed/3BFChzvx3783jGUKgHVCanFVxyDAn5xT3Y5NL5FKydVMuBa7Bm/72723/675
    "/{net}/account/rewards-bucketed/{account_id}/{account_index}/{width}",
    response_class=Response,
)
async def account_rewards_bucketed(
    request: Request,
    net: str,
    account_id: str,
    account_index: int,
    width: int,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    tags: dict = Depends(get_labeled_accounts),
):
    if net == "mainnet":
        pp = [
            {"$match": {"account_id": account_id}},
        ]
        result_pp = list(mongodb.mainnet[Collections.paydays_rewards].aggregate(pp))
        ff = [
            {
                "date": x["date"],
                "Transaction Fees": x["reward"]["transaction_fees"] / 1_000_000,
                "Validation Reward": x["reward"]["baker_reward"] / 1_000_000,
                "Finalization Reward": x["reward"]["finalization_reward"] / 1_000_000,
                # "total_reward": x["reward"]["transaction_fees"]+ x["reward"]["baker_reward"]+x["reward"]["finalization_reward"],
            }
            for x in result_pp
        ]
        df = pd.DataFrame(ff)
        if len(df) > 0:
            df["date"] = pd.to_datetime(df["date"])
            df_group = (
                df.groupby([pd.Grouper(key="date", axis=0, freq="ME")])
                .sum()
                .reset_index()
            )
            melt = pd.melt(
                df_group,
                id_vars=["date"],
                value_vars=[
                    "Transaction Fees",
                    "Validation Reward",
                    "Finalization Reward",
                ],
            )

            base = alt.Chart(melt)
            rng = [
                "#6E97F7",
                "#AE7CF7",
                "#70B785",
            ]

            bar = base.mark_bar(
                cornerRadiusTopLeft=3,
                cornerRadiusTopRight=3,
                size=15 if width < 400 else 25,
            ).encode(
                alt.X("date:T", scale=alt.Scale(nice=True)),
                y=alt.Y(
                    "value:Q",
                    title="CCD",
                    scale=alt.Scale(nice=True),
                    axis=alt.Axis(
                        grid=False,
                        #    offset=10,
                        format=".2s",
                    ),
                ),
                color=alt.Color(
                    "variable:N", title="Reward Type", scale=alt.Scale(range=rng)
                ),
                tooltip=[
                    alt.Tooltip("date:T", title="Month Ending"),
                    alt.Tooltip("variable:N", title="Reward Type"),
                    alt.Tooltip("value:Q", title="Amount (CCD)", format=",.0f"),
                ],
            )
            chart = bar.properties(
                # width='container',
                width=width * 0.80 if width < 400 else width,
                height=200,
                title={
                    "text": "Rewards from staking/delegation per month",
                    "subtitle": f"Account {account_index}",
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
            return chart.to_json(format="vega")
        else:
            return ""
    else:
        return ""


@router.get(
    "/account/baker-performance/{net}/{bakerId}/{days}/{width}", response_class=Response
)
async def account_baker_performance_graph(
    request: Request,
    net: str,
    bakerId: str,
    days: int,
    width: int,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    tags: dict = Depends(get_labeled_accounts),
):
    if net == "mainnet":
        show_x_number_of_days = days
        baker_id = bakerId
        result = list(
            mongodb.mainnet[Collections.paydays_performance]
            .find({"baker_id": str(baker_id)})
            .sort("date", ASCENDING)
        )
        df_source = pd.json_normalize(result).reset_index()
        df = df_source.copy().tail(show_x_number_of_days)
        period_string = (
            "all data"
            if len(df) == len(result)
            else f"last {show_x_number_of_days:,.0f} days"
        )
        df["Sum (actually baked)"] = df[
            "pool_status.current_payday_info.blocks_baked"
        ].cumsum()
        df["Sum (expectation)"] = df["expectation"].cumsum()
        df = df[["date", "Sum (actually baked)", "Sum (expectation)"]]
        df.columns = ["date", "Sum (validated)", "Sum (expectation)"]
        df_cumsum = df.melt("date", var_name="var", value_name="value")
        rng = ["#70B785", "#AE7CF7"]
        f_actual = df_cumsum["var"] == "Sum (validated)"
        f_expect = df_cumsum["var"] == "Sum (expectation)"

        actual = (
            alt.Chart(df_cumsum[f_actual])
            .mark_area(line={"color": "#AE7CF7"}, opacity=0.5)
            .encode(
                x=alt.X("date:T", axis=alt.Axis(grid=False, title="")),
                y=alt.Y(
                    "value:Q", axis=alt.Axis(grid=False, title="Blocks"), stack=None
                ),
                color=alt.Color(
                    "var:N",
                    title="Blocks for validator",  # , scale=alt.Scale(range=rng)
                ),
            )
        )

        expect = (
            alt.Chart(df_cumsum[f_expect])
            .mark_line(opacity=1)
            .encode(
                x=alt.X("date:T", axis=alt.Axis(grid=False, title="")),
                y=alt.Y(
                    "value:Q",
                    axis=alt.Axis(grid=False, title="Blocks", orient="right"),
                    stack=None,
                ),
                color=alt.Color(
                    "var:N", title="Blocks for validator", scale=alt.Scale(range=rng)
                ),
            )
        )
        chart = (
            (actual + expect)
            .properties(
                # width='container',
                width=width * 0.80 if width < 400 else width,
                height=200,
                title={
                    "text": f"Validator Performance ({period_string})",
                    "subtitle": f"Validator {bakerId}",
                },
            )
            .configure_legend(
                orient="top-left",
                direction="vertical",
                fillColor="white",
                padding=15,
                labelPadding=15,
                strokeColor="gray",
                labelFontSize=9,
            )
        )

        return chart.to_json(format="vega")
    else:
        return ""


def apy_graph(_id: str, width: int, mongodb: MongoDB) -> json:
    result = mongodb.mainnet[Collections.paydays_apy_intermediate].find_one(
        {"_id": {"$eq": str(_id)}}
    )
    if result:
        if "d30_apy_dict" in result:
            d30_apy_dict = (
                {k: v["apy"] for k, v in result["d30_apy_dict"].items()}
                if result["d30_apy_dict"] is not None
                else None
            )
        else:
            d30_apy_dict = None
        if "d90_apy_dict" in result:
            d90_apy_dict = (
                {k: v["apy"] for k, v in result["d90_apy_dict"].items()}
                if result["d90_apy_dict"] is not None
                else None
            )
        else:
            d90_apy_dict = None
        if "d180_apy_dict" in result:
            d180_apy_dict = (
                {k: v["apy"] for k, v in result["d180_apy_dict"].items()}
                if result["d180_apy_dict"] is not None
                else None
            )
        else:
            d180_apy_dict = None

        if d30_apy_dict:
            df_30d = pd.DataFrame.from_dict(d30_apy_dict, orient="index").reset_index()
            df_30d.columns = ["date", "30d"]
        if d90_apy_dict:
            df_90d = pd.DataFrame.from_dict(d90_apy_dict, orient="index").reset_index()
            df_90d.columns = ["date", "90d"]
        if d180_apy_dict:
            df_180d = pd.DataFrame.from_dict(
                d180_apy_dict, orient="index"
            ).reset_index()
            df_180d.columns = ["date", "180d"]

        if d180_apy_dict:
            df = pd.merge(
                pd.merge(df_30d, df_90d, on="date", how="outer"),
                df_180d,
                on="date",
                how="outer",
            ).melt("date")
        elif d90_apy_dict:
            df = pd.merge(df_30d, df_90d, on="date", how="outer").melt("date")
        elif d30_apy_dict:
            df = df_30d.melt("date")
        else:
            df = None

        days_alive = (
            dt.datetime.now() - dt.datetime(2022, 6, 24, 9, 0, 0)
        ).total_seconds() / (60 * 60 * 24)
        domain_pd = pd.to_datetime(
            [
                dt.date(2022, 6, 24) + dt.timedelta(days=x)
                for x in range(0, int(days_alive + 1))
            ]
        )
        if df is None:
            return None

        chart = (
            alt.Chart(df)
            .mark_line(opacity=1)
            .encode(
                x=alt.X(
                    "date:T",
                    scale=alt.Scale(domain=list(domain_pd)),
                    axis=alt.Axis(grid=False, title=""),
                ),
                y=alt.Y(
                    "value:Q",
                    scale=alt.Scale(domain=[0.08, 0.18]),
                    axis=alt.Axis(grid=False, format="%", title="APY", orient="right"),
                    stack=None,
                ),
                color=alt.Color(
                    "variable:N",
                    title="Period",
                    sort=["30d"],
                    scale=alt.Scale(range=["#AE7CF7", "#70B785", "#6E97F7"]),
                ),
            )
        )
        to_return = chart.properties(
            # width='container',
            width=width * 0.80 if width < 400 else width,
            height=200,
            title={
                "text": (
                    "Moving Averages for Delegator APY"
                    if str(_id).isnumeric()
                    else "Moving Averages for Account APY"
                ),
                "subtitle": (
                    f"Baker/pool {_id}"
                    if str(_id).isnumeric()
                    else f"{_id[:6]}...{_id[(len(_id)-6):]}"
                ),
            },
        ).configure_legend(
            orient="top-left",
            direction="vertical",
            fillColor="white",
            padding=15,
            labelPadding=15,
            strokeColor="gray",
            labelFontSize=9,
        )

        return to_return.to_json(format="vega")
    else:
        return None


@router.get("/account/apy-graph/{net}/{_id}/{width}", response_class=Response)
async def account_apy_graph(
    request: Request,
    net: str,
    _id: str,
    width: int,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    if net == "mainnet":
        return apy_graph(_id, width, mongodb)
    else:
        return ""


@router.get("/account/baker-tally/{net}/{account_id}", response_class=HTMLResponse)
async def account_baker_tally(
    request: Request,
    net: str,
    account_id: str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
):
    if net == "mainnet":
        account_info = grpcclient.get_account_info(
            block_hash="last_final", hex_address=account_id
        )

        if account_info.stake:
            if account_info.stake.baker:
                baker_id = account_info.stake.baker.baker_info.baker_id
            else:
                baker_id = None
        else:
            baker_id = None

        if baker_id:
            result = list(
                mongodb.mainnet[Collections.paydays_performance]
                .find({"baker_id": str(baker_id)})
                .sort("date", ASCENDING)
            )

            data = {
                v["date"]: {
                    "actuals": v["pool_status"]["current_payday_info"]["blocks_baked"],
                    "lp": v["pool_status"]["current_payday_info"]["lottery_power"],
                    "expectation": v["expectation"],
                }
                for v in result
            }
            # data = pd.DataFrame.from_dict(bake_rates).T.reset_index()
            # data = dict(sorted(data.items()))
            html = templates.get_template("/account/account_baker_tally.html").render(
                {"data": data}
            )
            return html
        else:
            return None
    else:
        return ""


def get_reward_object(lookup_value: str, mongodb: MongoDB):
    raw_apy_object = mongodb.mainnet[Collections.paydays_apy_intermediate].find_one(
        {"_id": lookup_value}
    )
    lookup_apy_object = {
        "d30": {"sum_of_rewards": 0, "apy": 0},
        "d90": {"sum_of_rewards": 0, "apy": 0},
        "d180": {"sum_of_rewards": 0, "apy": 0},
    }
    if raw_apy_object:
        if "d30_apy_dict" in raw_apy_object:
            if raw_apy_object["d30_apy_dict"] is not None:
                d30_day = list(raw_apy_object["d30_apy_dict"].keys())[-1]
                lookup_apy_object["d30"] = raw_apy_object["d30_apy_dict"][d30_day]

        if "d90_apy_dict" in raw_apy_object:
            if raw_apy_object["d90_apy_dict"] is not None:
                d90_day = list(raw_apy_object["d90_apy_dict"].keys())[-1]
                lookup_apy_object["d90"] = raw_apy_object["d90_apy_dict"][d90_day]

        if "d180_apy_dict" in raw_apy_object:
            if raw_apy_object["d180_apy_dict"] is not None:
                d180_day = list(raw_apy_object["d180_apy_dict"].keys())[-1]
                lookup_apy_object["d180"] = raw_apy_object["d180_apy_dict"][d180_day]

    return lookup_apy_object


@router.get("/account/{value}", response_class=RedirectResponse)
async def redirect_account_to_mainnet(request: Request, value: str):
    response = RedirectResponse(url=f"/mainnet/account/{value}", status_code=302)
    return response


@router.get(
    "/ajax_earliest_win_time/{net}/account_index/{account_index}",
    response_class=HTMLResponse,
)
async def ajax_earliest_win_time(
    request: Request,
    net: str,
    account_index: int,
    grpcclient: GRPCClient = Depends(get_grpcclient),
):
    earliest_win_time = grpcclient.get_baker_earliest_win_time(account_index)
    return f"{earliest(earliest_win_time)}"


@router.get(
    "/ajax_current_payday_stats/{net}/account_index/{account_index}",
    response_class=HTMLResponse,
)
async def ajax_payday_stats(
    request: Request,
    net: str,
    account_index: int,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    paydays_last_blocks_validated=Depends(get_paydays_per_day),
):
    pool = grpcclient.get_pool_info_for_pool(account_index, "last_final", net=NET(net))
    stats = expectation(
        pool.current_payday_info.lottery_power * paydays_last_blocks_validated,
        pool.current_payday_info.blocks_baked,
    )
    return stats


class ExplorerTab(BaseModel):
    display_name: str
    active: bool = False
    children: Optional[dict[str, ExplorerTab]] = None


account_tabs = {
    "info": ExplorerTab(
        display_name="Info",
        active=True,
        children={
            "general": ExplorerTab(display_name="General", active=True),
            "flow": ExplorerTab(display_name="Flow Graph"),
        },
    ),
    "identity": ExplorerTab(
        display_name="Identity",
    ),
    "rewards-no-stake": ExplorerTab(
        display_name="Rewards",
    ),
    "delegation": ExplorerTab(
        display_name="Delegation",
        children={
            "info": ExplorerTab(display_name="Info", active=True),
            "rewards": ExplorerTab(display_name="Rewards"),
            "apy": ExplorerTab(display_name="APY over Time"),
        },
    ),
    "validator": ExplorerTab(
        display_name="Validator",
        children={
            "info": ExplorerTab(display_name="Info", active=True),
            "rewards": ExplorerTab(display_name="Rewards"),
            "performance": ExplorerTab(display_name="Performance"),
            "tally": ExplorerTab(display_name="Tally"),
            "apy": ExplorerTab(display_name="APY over Time"),
        },
    ),
    "pool": ExplorerTab(
        display_name="Pool",
        children={
            "info": ExplorerTab(display_name="Info", active=True),
            "rewards": ExplorerTab(display_name="Rewards"),
            "delegators": ExplorerTab(display_name="Delegators"),
            "apy": ExplorerTab(display_name="APY over Time"),
        },
    ),
    "tokens": ExplorerTab(
        display_name="Tokens",
    ),
    "txs": ExplorerTab(
        display_name="Txs",
    ),
}


def set_tabs(
    defaults: dict[str, ExplorerTab],
    available_tabs: dict[str, bool],
    chosen_tab: str | None,
    chosen_subtab: str | None,
) -> dict[str, ExplorerTab]:
    d = copy.deepcopy(defaults)
    if d.get(chosen_tab) and available_tabs.get(chosen_tab):
        for tab_name in d:
            d[tab_name].active = tab_name == chosen_tab
        if d[chosen_tab].children:
            if d[chosen_tab].children.get(chosen_subtab):
                for subtab_name in d[chosen_tab].children:
                    d[chosen_tab].children[subtab_name].active = (
                        subtab_name == chosen_subtab
                    )
            else:
                sub_tabs = list(d[chosen_tab].children.keys())
                d[chosen_tab].children[sub_tabs[0]].active = True
        return d
    else:
        return defaults


@router.get("/{net}/account/{value}", response_class=HTMLResponse)
async def get_account(
    request: Request,
    net: str,
    value: str,
    tab: Optional[str] = "info",
    subtab: Optional[str] = "general",
    fragment: Optional[str] = None,
    show_tab: str = None,
    recurring: Recurring = Depends(get_recurring),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    mongodb: MongoDB = Depends(get_mongo_db),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
    exchange_rates: dict = Depends(get_exchange_rates),
):
    account_id = None
    account_index = None
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    if len(value) == 29:
        result = db_to_use[Collections.nightly_accounts].find(
            {"_id": {"$regex": f"{value}"}}
        )
        the_list = list(result)
        if len(the_list) > 0:
            value = the_list[0]["account"]
            account_id = the_list[0]["account"]
            account_index = the_list[0]["index"]

    if len(value) == 50:
        try:
            account_info = grpcclient.get_account_info(
                block_hash="last_final", hex_address=value, net=NET(net)
            )
            account_id = account_info.address
            account_index = account_info.index
        except:
            account_info = None

    elif value.isnumeric():
        try:
            account_info = grpcclient.get_account_info(
                block_hash="last_final", account_index=int(value), net=NET(net)
            )
            account_id = account_info.address
            account_index = account_info.index
        except:
            account_info = None
    else:
        account_info = None

    if not account_info:
        error = {
            "error": True,
            "errorMessage": f"No account on {net} found at {value}.",
        }
        return templates.TemplateResponse(
            "account/account_account_error.html",
            {"env": request.app.env, "request": request, "net": net, "error": error},
        )
    else:
        error = None
        # account_id = account_info.address
        if account_info.stake:
            delegation = account_info.stake.delegator
            baker_id = (
                account_info.stake.baker.baker_info.baker_id
                if account_info.stake.baker
                else None
            )
        else:
            delegation = None
            baker_id = None

        identity = Identity(account_info)

        tag_found, tag_label = account_tag(account_id, user, tags, header=True)

        delegation_target_address = None
        account_apy_object = None
        if delegation:
            delegation_target_address = delegation.target
            account_apy_object = get_reward_object(account_id, mongodb)

        if baker_id:
            account_is_baker = True

            possible_block = baker_id
            pool = grpcclient.get_pool_info_for_pool(
                baker_id, "last_final", net=NET(net)
            )
            node = db_to_use[Collections.dashboard_nodes].find_one(
                {"consensusBakerId": str(baker_id)}
            )
            earliest_win_time = grpcclient.get_baker_earliest_win_time(baker_id)
            pool_apy_object = get_reward_object(str(baker_id), mongodb)
            account_apy_object = get_reward_object(account_id, mongodb)

        else:
            possible_block = -1
            account_is_baker = False
            pool = None
            node = None
            performance_results = None
            pool_apy_object = None
            earliest_win_time = None

        result = mongodb.mainnet[Collections.paydays_rewards].find_one(
            {"account_id": account_id}
        )
        if result:
            rewards_for_account_available = True
        else:
            rewards_for_account_available = False

        result = db_to_use[Collections.tokens_links_v2].find(
            {"account_address_canonical": account_id[:29]}
        )
        if len(result_list := list(result)) > 0:
            tokens_available = True
            tokens_with_metadata, tokens_value_USD = add_metadata_to_single_tokens(
                {
                    x["token_holding"]["contract"]: x["token_holding"]
                    for x in result_list
                },
                db_to_use,
                exchange_rates,
            )
        else:
            tokens_available = False
            tokens_value_USD = 0

        # TODO
        accounts_for_download = []
        # accounts_for_download = (
        #     [account.account_id for account in user.accounts.values()] if user else None
        # )
        cns_domains_list = None  # cns_domains_registered(account_id)

    available_tabs = {
        "info": True,
        "identity": True,
        "rewards-no-stake": (account_info.stake.baker is None)
        and (account_info.stake.delegator is None)
        and rewards_for_account_available,
        "validator": account_is_baker,
        "delegation": delegation is not None,
        "pool": pool is not None,
        "tokens": tokens_available,
        "txs": True,
    }

    tabs = set_tabs(account_tabs, available_tabs, tab, subtab)
    return templates.TemplateResponse(
        "account/account_account.html",
        {
            "env": request.app.env,
            "tabs": tabs,
            "rewards_no_stake": (account_info.stake.baker is None)
            and (account_info.stake.delegator is None)
            and rewards_for_account_available,
            "rewards_for_account_available": rewards_for_account_available,
            "account_id": account_id,
            "account_index": account_index,
            # "fragment": fragment,
            "request": request,
            "exchange_rates": exchange_rates,
            "tokens_value_USD": tokens_value_USD,
            "pool_apy_object": pool_apy_object,
            "account_apy_object": account_apy_object,
            "account": account_info,
            "pool": pool,
            "show_tab": show_tab,
            "earliest_win_time": earliest_win_time,
            "node": node,
            "account_is_baker": account_is_baker,
            "cns_domains_list": cns_domains_list,
            "identity": identity,
            "recurring": recurring,
            "accounts_for_download": accounts_for_download,
            "delegation": delegation,
            "delegation_target_address": delegation_target_address,
            "error": error,
            "net": net,
            "user": user,
            "tags": tags,
            "possible_block": possible_block,
            "tag_found": tag_found,
            "tag_label": tag_label,
            "tokens_available": tokens_available,
        },
    )


@router.get(
    "/ajax_account_html/{net}/{account_id}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_account_html(
    request: Request,
    net: str,
    account_id: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    recurring: Recurring = Depends(get_recurring),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    mongodb: MongoDB = Depends(get_mongo_db),
    tags: dict = Depends(get_labeled_accounts),
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    contracts_with_tag_info: dict = Depends(get_contracts_with_tag_info),
    ccd_historical: dict = Depends(get_exchange_rates_ccd_historical),
    # token_addresses_with_markup: dict = Depends(get_token_addresses_with_markup),
    credential_issuers: list = Depends(get_credential_issuers),
):
    """
    Add {net}.
    """
    limit = 20
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet

    if api_key != request.app.env["API_KEY"]:
        return "No valid api key supplied."
    else:
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

        top_list_member = await db_to_use[
            Collections.impacted_addresses_all_top_list
        ].find_one({"_id": account_id[:29]})

        if not top_list_member:
            pipeline = [
                {
                    "$match": {"impacted_address_canonical": {"$eq": account_id[:29]}},
                },
                {  # this filters out account rewards, as they are special events
                    "$match": {"tx_hash": {"$exists": True}},
                },
                {"$sort": {"block_height": DESCENDING}},
                {"$project": {"_id": 0, "tx_hash": 1}},
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
                await db_to_use[Collections.impacted_addresses]
                .aggregate(pipeline)
                .to_list(limit)
            )
            all_txs_hashes = [x["tx_hash"] for x in result[0]["data"]]
            if "total" in result[0]:
                total_tx_count = result[0]["total"]
            else:
                total_tx_count = 0

        else:
            #### This is a TOP_TX_COUNT account
            pipeline = [
                {
                    "$match": {"impacted_address_canonical": {"$eq": account_id[:29]}},
                },
                {  # this filters out account rewards, as they are special events
                    "$match": {"tx_hash": {"$exists": True}},
                },
                {"$sort": {"block_height": DESCENDING}},
                {"$skip": skip},
                {"$limit": limit},
                {"$project": {"tx_hash": 1}},
            ]
            result = (
                await db_to_use[Collections.impacted_addresses]
                .aggregate(pipeline)
                .to_list(limit)
            )
            all_txs_hashes = [x["tx_hash"] for x in result]
            total_tx_count = top_list_member["count"]

        int_result = (
            await db_to_use[Collections.transactions]
            .find({"_id": {"$in": all_txs_hashes}})
            .sort("block_info.height", DESCENDING)
            .to_list(limit)
        )
        tx_result = [CCD_BlockItemSummary(**x) for x in int_result]

        if len(tx_result) > 0:
            for transaction in tx_result:
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
            total_tx_count,
            requested_page,
            tx_tabs,
            tx_tabs_active,
            block_transactions=False,
        )

        for tab in TransactionClassifier:
            html += process_transactions_to_HTML(
                tx_tabs[tab], tab.value, tx_tabs_active[tab], tags
            )

        html += transactions_html_footer()
        return html


@router.get(
    "/ajax_delegators_html_v2/{account_id}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_delegators_html_v2(
    request: Request,
    account_id: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    recurring: Recurring = Depends(get_recurring),
    tags: dict = Depends(get_labeled_accounts),
):
    limit = 20
    user: UserV2 = get_user_detailsv2(request)
    if api_key != request.app.env["API_KEY"]:
        return "No valid api key supplied."
    else:
        account_info = grpcclient.get_account_info(
            block_hash="last_final", hex_address=account_id
        )
        baker = account_info.stake.baker
        if baker:
            if requested_page > -1:
                skip = requested_page * limit
            else:
                nr_of_pages, _ = divmod(total_rows, limit)
                skip = nr_of_pages * limit

            try:
                delegators_current_payday = [
                    x
                    for x in grpcclient.get_delegators_for_pool_in_reward_period(
                        baker.baker_info.baker_id, "last_final"
                    )
                ]
            except:
                delegators_current_payday = []

            try:
                delegators_in_block = [
                    x
                    for x in grpcclient.get_delegators_for_pool(
                        baker.baker_info.baker_id, "last_final"
                    )
                ]
            except:
                delegators_in_block = []

            delegators_in_dict = {x.account: x for x in delegators_in_block}

            delegators_current_payday_list = set(
                [x.account for x in delegators_current_payday]
            )
            delegators_in_block_list = set([x.account for x in delegators_in_block])

            delegators_current_payday_dict = {
                x.account: x for x in delegators_current_payday
            }
            delegators_in_block_dict = {x.account: x for x in delegators_in_block}

            new_delegators = delegators_in_block_list - delegators_current_payday_list
            new_delegators_dict = {x: delegators_in_dict[x] for x in new_delegators}

            delegators = sorted(
                delegators_current_payday, key=lambda x: x.stake, reverse=True
            )
            html = process_delegators_to_HTML_v2(
                request,
                delegators[skip : (skip + limit)],
                len(delegators),
                requested_page,
                None,
                None,
                delegators_current_payday_dict,
                delegators_in_block_dict,
                new_delegators_dict,
            )
            return html


@router.get(
    "/ajax_account_tokens/{net}/{address}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_tokens(
    request: Request,
    net: str,
    address: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    contracts_with_tag_info: dict = Depends(get_contracts_with_tag_info),
    # exchange_rates: dict = Depends(get_exchange_rates),
    # token_addresses_with_markup: dict = Depends(get_token_addresses_with_markup),
):
    limit = 20
    # user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    if api_key != request.app.env["API_KEY"]:
        return "No valid api key supplied."
    else:
        if requested_page > -1:
            skip = requested_page * limit
        else:
            nr_of_pages, _ = divmod(total_rows, limit)
            skip = nr_of_pages * limit

        total_count_row = db_to_use[Collections.pre_tokens_by_address].find_one(
            {"_id": address[:29]}
        )
        if total_count_row:
            total_pipeline_query = {
                "$facet": {"data": [{"$skip": skip}, {"$limit": limit}]}
            }
        else:
            total_pipeline_query = {
                "$facet": {
                    "metadata": [{"$count": "total"}],
                    "data": [{"$skip": skip}, {"$limit": limit}],
                }
            }

        pipeline = [
            {"$match": {"account_address_canonical": address[:29]}},
            {"$sort": {"token_holding.token_address": DESCENDING}},
        ]
        pipeline.append(total_pipeline_query)

        result_list = list(db_to_use[Collections.tokens_links_v2].aggregate(pipeline))
        if not total_count_row:
            total_count = result_list[0]["metadata"][0]["total"]
        else:
            total_count = total_count_row["count"]
        tokens = {
            x["token_holding"]["token_address"]: x["token_holding"]
            for x in result_list[0]["data"]
        }

        if tokens:
            token_addresses_with_markup = {
                x["_id"]: x
                for x in db_to_use[Collections.tokens_token_addresses_v2].find(
                    {"_id": {"$in": list(tokens.keys())}}
                )
            }

            for token_address, token in tokens.items():
                # this needs to be a lookup in pre_ for all tokens at once and then locally generate this dict
                token_address_with_markup: MongoTypeTokenAddress | None = (
                    token_addresses_with_markup.get(token_address)
                )
                if not isinstance(token_address_with_markup, MongoTypeTokenAddress):
                    token_address_with_markup = MongoTypeTokenAddress(
                        **token_address_with_markup
                    )
                if token_address_with_markup:
                    if token_address_with_markup.token_id == "":
                        tokens[token_address].update({"token_type": "fungible"})
                    else:
                        tokens[token_address].update({"token_type": "non-fungible"})
                    tokens[token_address].update(
                        {"token_metadata": token_address_with_markup.token_metadata}
                    )
                    tokens_tag_info_from_contract = contracts_with_tag_info.get(
                        token_address_with_markup.contract
                    )
                    if tokens_tag_info_from_contract:
                        tokens[token_address].update(
                            {"tag_info": tokens_tag_info_from_contract}
                        )
                    else:
                        tokens[token_address].update({"tag_info": None})
                    if token_address_with_markup.exchange_rate:
                        tokens[token_address].update(
                            {
                                "token_value": int(
                                    tokens[token_address]["token_amount"]
                                )
                                * (
                                    math.pow(
                                        10,
                                        -tokens_tag_info_from_contract.decimals,
                                    )
                                )
                            }
                        )
                        tokens[token_address].update(
                            {
                                "token_value_USD": tokens[token_address]["token_value"]
                                * token_address_with_markup.exchange_rate
                            }
                        )
                        tokens[token_address].update(
                            {"exchange_rate": token_address_with_markup.exchange_rate}
                        )
        else:
            tokens = {}
            len_tokens = 0

        fung_count = 0
        non_fung_count = 0
        for token in tokens.values():
            if token["token_type"] == "fungible":
                fung_count += 1
            if token["token_type"] == "non-fungible":
                non_fung_count += 1
        html = process_tokens_to_HTML_v2(
            tokens,
            total_count,
            requested_page,
            None,
            None,
            net,
            fung_count,
            non_fung_count,
        )
        return html


@router.get(
    "/ajax_account_tokens_fungible/{net}/{address}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_tokens_fungible(
    request: Request,
    net: str,
    address: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    contracts_with_tag_info: dict = Depends(get_contracts_with_tag_info),
    # exchange_rates: dict = Depends(get_exchange_rates),
    # token_addresses_with_markup: dict = Depends(get_token_addresses_with_markup),
):
    limit = 20
    # user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    if api_key != request.app.env["API_KEY"]:
        return "No valid api key supplied."
    else:
        if requested_page > -1:
            skip = requested_page * limit
        else:
            nr_of_pages, _ = divmod(total_rows, limit)
            skip = nr_of_pages * limit

        result_list = list(
            db_to_use[Collections.tokens_links_v2].find(
                {"account_address_canonical": address[:29]}
            )
        )
        tokens = {
            x["token_holding"]["token_address"]: x["token_holding"] for x in result_list
        }

        if tokens:
            token_addresses = list(tokens.keys())
            token_addresses_with_markup = get_token_addresses_with_markup_for_addresses(
                token_addresses, request, db_to_use
            )
            # tokens: dict = result["tokens"]
            len_tokens = len(tokens)

            token_addresses_to_display = token_addresses[skip : (skip + limit)]
            t_all = set(token_addresses)
            t_display = set(token_addresses_to_display)
            t_adr_to_remove = list(t_all - t_display)
            for k in t_adr_to_remove:
                tokens.pop(k, None)

            for token_address, token in tokens.items():
                # this needs to be a lookup in pre_ for all tokens at once and then locally generate this dict
                token_address_with_markup = token_addresses_with_markup[token_address]
                tokens[token_address].update({"markup": token_address_with_markup})
                if token_address_with_markup.tag_information:
                    if (
                        token_address_with_markup.tag_information.token_type
                        == "fungible"
                    ):
                        tokens[token_address].update(
                            {
                                "token_value": int(
                                    tokens[token_address]["token_amount"]
                                )
                                * (
                                    math.pow(
                                        10,
                                        -token_address_with_markup.tag_information.decimals,
                                    )
                                )
                            }
                        )
                        tokens[token_address].update(
                            {
                                "token_value_USD": tokens[token_address]["token_value"]
                                * token_address_with_markup.exchange_rate
                            }
                        )
        else:
            tokens = {}
            len_tokens = 0

        fung_count = 0
        non_fung_count = 0
        for token in tokens.values():
            if token["markup"].tag_information:
                if token["markup"].tag_information.token_type == "fungible":
                    fung_count += 1
                if token["markup"].tag_information.token_type == "non-fungible":
                    non_fung_count += 1
        html = process_tokens_to_HTML_v2(
            tokens,
            len_tokens,
            requested_page,
            None,
            None,
            net,
            fung_count,
            non_fung_count,
        )
        return html


@router.get(
    "/ajax_account_tokens_nft/{net}/{address}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_tokens_nft(
    request: Request,
    net: str,
    address: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    contracts_with_tag_info: dict = Depends(get_contracts_with_tag_info),
    # exchange_rates: dict = Depends(get_exchange_rates),
    # token_addresses_with_markup: dict = Depends(get_token_addresses_with_markup),
):
    limit = 20
    # user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    if api_key != request.app.env["API_KEY"]:
        return "No valid api key supplied."
    else:
        if requested_page > -1:
            skip = requested_page * limit
        else:
            nr_of_pages, _ = divmod(total_rows, limit)
            skip = nr_of_pages * limit

        # result = db_to_use[Collections.tokens_accounts].find_one({"_id": address})
        result_list = list(
            db_to_use[Collections.tokens_links_v2].find(
                {"account_address_canonical": address[:29]}
            )
        )
        tokens = {
            x["token_holding"]["token_address"]: x["token_holding"] for x in result_list
        }

        if tokens:
            token_addresses = list(tokens.keys())
            token_addresses_with_markup = get_token_addresses_with_markup_for_addresses(
                token_addresses, request, db_to_use
            )
            # tokens: dict = result["tokens"]
            len_tokens = len(tokens)

            token_addresses_to_display = token_addresses[skip : (skip + limit)]
            t_all = set(token_addresses)
            t_display = set(token_addresses_to_display)
            t_adr_to_remove = list(t_all - t_display)
            for k in t_adr_to_remove:
                tokens.pop(k, None)

            for token_address, token in tokens.items():
                # this needs to be a lookup in pre_ for all tokens at once and then locally generate this dict
                token_address_with_markup = token_addresses_with_markup[token_address]
                tokens[token_address].update({"markup": token_address_with_markup})
                if token_address_with_markup.tag_information:
                    if (
                        token_address_with_markup.tag_information.token_type
                        == "fungible"
                    ):
                        tokens[token_address].update(
                            {
                                "token_value": int(
                                    tokens[token_address]["token_amount"]
                                )
                                * (
                                    math.pow(
                                        10,
                                        -token_address_with_markup.tag_information.decimals,
                                    )
                                )
                            }
                        )
                        tokens[token_address].update(
                            {
                                "token_value_USD": tokens[token_address]["token_value"]
                                * token_address_with_markup.exchange_rate
                            }
                        )
        else:
            tokens = {}
            len_tokens = 0

        non_fung_count = 0
        for token in tokens.values():
            if token["markup"].tag_information:
                if token["markup"].tag_information.token_type == "non-fungible":
                    non_fung_count += 1
        html = process_tokens_to_HTML_v2(
            tokens,
            len_tokens,
            requested_page,
            None,
            None,
            net,
            fung_count,
            non_fung_count,
        )
        return html
