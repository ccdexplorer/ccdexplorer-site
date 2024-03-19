from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse

from app.jinja2_helpers import *
from env import *
from ccdefundamentals.GRPCClient import GRPCClient

from ccdefundamentals.mongodb import (
    MongoDB,
    MongoMotor,
    Collections,
    MongoTypePayday,
    MongoTypePaydaysPerformance,
)
from app.Recurring.recurring import Recurring
from app.state.state import *
from app.ajax_helpers import (
    transactions_html_footer,
    process_paydays_to_HTML_v2,
    process_passive_delegators_to_HTML_v2,
    process_sorted_pools_to_HTML_v2,
)
import math
from ccdefundamentals.user_v2 import UserV2, NotificationPreferences
from ccdefundamentals.tooter import Tooter, TooterType, TooterChannel

router = APIRouter()


@router.get("/{net}/staking")  # type:ignore
async def staking(
    request: Request,
    net: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
):
    user: UserV2 = get_user_detailsv2(request)
    passive_delegation_apy_object = mongodb.mainnet[
        Collections.paydays_apy_intermediate
    ].find_one({"_id": "passive_delegation"})
    passive_object = {
        "d30": {"sum_of_rewards": 0, "apy": 0},
        "d90": {"sum_of_rewards": 0, "apy": 0},
        "d180": {"sum_of_rewards": 0, "apy": 0},
    }
    if passive_delegation_apy_object:
        d30_day = list(passive_delegation_apy_object["d30_apy_dict"].keys())[-1]
        d90_day = list(passive_delegation_apy_object["d90_apy_dict"].keys())[-1]
        d180_day = list(passive_delegation_apy_object["d180_apy_dict"].keys())[-1]

        passive_object["d30"] = passive_delegation_apy_object["d30_apy_dict"][d30_day]
        passive_object["d90"] = passive_delegation_apy_object["d90_apy_dict"][d90_day]
        passive_object["d180"] = passive_delegation_apy_object["d180_apy_dict"][
            d180_day
        ]

    passive_info_v2 = grpcclient.get_passive_delegation_info("last_final")
    if net == "mainnet":
        return templates.TemplateResponse(
            "staking/staking.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "passive_object": passive_object,
                "passive_info_v2": passive_info_v2,
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


@router.get(
    "/ajax_paydays_html_v2/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_paydays_html_v2(
    request: Request,
    requested_page: int,
    total_rows: int,
    api_key: str,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    limit = 20

    if api_key != request.app.env["API_KEY"]:
        return "No valid api key supplied."
    else:
        # requested page = 0 indicated the first page
        # requested page = -1 indicates the last page
        if requested_page > -1:
            skip = requested_page * limit
        else:
            nr_of_pages, _ = divmod(total_rows, limit)
            skip = nr_of_pages * limit

        result = list(
            mongodb.mainnet[Collections.paydays].aggregate(
                [
                    {"$sort": {"date": -1}},
                    {
                        "$facet": {
                            "metadata": [{"$count": "total"}],
                            "data": [{"$skip": int(skip)}, {"$limit": int(limit)}],
                        }
                    },
                ]
            )
        )[0]

        reward_result = [MongoTypePayday(**x) for x in result["data"]]
        html = process_paydays_to_HTML_v2(
            reward_result,
            result["metadata"][0]["total"],
            requested_page,
            None,
            None,
        )

        return html


async def get_pools(
    mongodb: MongoDB,
    mongomotor: MongoMotor,
    pools_for_status,
    last_payday: MongoTypePayday,
):
    start = dt.datetime.now()
    result = (
        await mongomotor.mainnet[Collections.paydays_current_payday]
        .find()
        .to_list(100_000)
    )
    console.log(f"1: {(dt.datetime.now()-start).total_seconds():,.12f}")
    start = dt.datetime.now()
    last_payday_performance = {
        x["baker_id"]: MongoTypePaydaysPerformance(
            **x
        )  # .model_dump(exclude_none=True)
        for x in result
        if (
            (str(x["baker_id"]).isnumeric())
            and (int(x["baker_id"]) in pools_for_status)
        )
    }
    console.log(f"2: {(dt.datetime.now()-start).total_seconds():,.12f}")
    start = dt.datetime.now()
    result = (
        await mongomotor.mainnet[Collections.paydays_apy_intermediate]
        .find({"_id": {"$in": list(last_payday_performance.keys())}})
        .to_list(100_000)
    )
    console.log(f"3: {(dt.datetime.now()-start).total_seconds():,.12f}")
    start = dt.datetime.now()
    last_payday_apy_objects = {x["_id"]: x for x in result}

    dd = {}
    for baker_id in last_payday_performance.keys():
        # print(baker_id)
        if "d30_apy_dict" in last_payday_apy_objects[baker_id]:
            if last_payday_apy_objects[baker_id]["d30_apy_dict"] is not None:
                d30_day = list(
                    last_payday_apy_objects[baker_id]["d30_apy_dict"].keys()
                )[-1]
            else:
                d30_day = None
        else:
            d30_day = None

        if "d90_apy_dict" in last_payday_apy_objects[baker_id]:
            if last_payday_apy_objects[baker_id]["d90_apy_dict"] is not None:
                d90_day = list(
                    last_payday_apy_objects[baker_id]["d90_apy_dict"].keys()
                )[-1]
            else:
                d90_day = None
        else:
            d90_day = None

        if "d180_apy_dict" in last_payday_apy_objects[baker_id]:
            if last_payday_apy_objects[baker_id]["d180_apy_dict"] is not None:
                d180_day = list(
                    last_payday_apy_objects[baker_id]["d180_apy_dict"].keys()
                )[-1]
            else:
                d180_day = None
        else:
            d180_day = None

        delegated_percentage = (
            (
                last_payday_performance[baker_id].pool_status.delegated_capital
                / last_payday_performance[baker_id].pool_status.delegated_capital_cap
            )
            * 100
            if last_payday_performance[baker_id].pool_status.delegated_capital_cap > 0
            else 0
        )

        delegated_percentage_remaining = 100 - delegated_percentage
        pie = (
            f"<style> .pie_{baker_id} {{\n"
            f"width: 20px;\nheight: 20px;\n"
            f"background-image: conic-gradient(#AE7CF7 0%, #AE7CF7 {delegated_percentage}%, #70B785 0%, #70B785 {delegated_percentage_remaining}%);\n"
            f" border-radius: 50%\n"
            f"}}\n</style>\n"
        )

        d = {
            "baker_id": baker_id,
            "block_commission_rate": last_payday_performance[
                baker_id
            ].pool_status.pool_info.commission_rates.baking,
            "tx_commission_rate": last_payday_performance[
                baker_id
            ].pool_status.pool_info.commission_rates.transaction,
            "expectation": last_payday_performance[baker_id].expectation,
            "lottery_power": last_payday_performance[
                baker_id
            ].pool_status.current_payday_info.lottery_power,
            "url": last_payday_performance[baker_id].pool_status.pool_info.url,
            "effective_stake": last_payday_performance[
                baker_id
            ].pool_status.current_payday_info.effective_stake,
            "delegated_capital": last_payday_performance[
                baker_id
            ].pool_status.delegated_capital,
            "delegated_capital_cap": last_payday_performance[
                baker_id
            ].pool_status.delegated_capital_cap,
            "baker_equity_capital": last_payday_performance[
                baker_id
            ].pool_status.current_payday_info.baker_equity_capital,
            "delegated_percentage": delegated_percentage,
            "delegated_percentage_remaining": delegated_percentage_remaining,
            "pie": pie,
            "d30": (
                last_payday_apy_objects[baker_id].get("d30_apy_dict")[d30_day]
                if d30_day
                else {"apy": 0.0, "sum_of_rewards": 0, "count_of_days": 0}
            ),
            "d90": (
                last_payday_apy_objects[baker_id].get("d90_apy_dict")[d90_day]
                if d90_day
                else {"apy": 0.0, "sum_of_rewards": 0, "count_of_days": 0}
            ),
            "d180": (
                last_payday_apy_objects[baker_id].get("d180_apy_dict")[d180_day]
                if d180_day
                else {"apy": 0.0, "sum_of_rewards": 0, "count_of_days": 0}
            ),
        }
        dd[baker_id] = d
    console.log(f"4: {(dt.datetime.now()-start).total_seconds():,.12f}")

    return dd


# This pagination works differently, as we are not requesting from the endpoint.
# Instead, we need to take a slice of a list.
@router.get(
    "/ajax_pools_html_v2/{status}/{key}/{direction}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_pools_html_v2(
    request: Request,
    status: str,
    key: str,
    direction: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    tags: dict = Depends(get_labeled_accounts),
):
    limit = 20
    user: UserV2 = get_user_detailsv2(request)
    if api_key != request.app.env["API_KEY"]:
        return "No valid api key supplied."
    else:
        last_payday = MongoTypePayday(
            **mongodb.mainnet[Collections.paydays].find_one(sort=[("date", -1)])
        )

        # requested page = 0 indicated the first page
        # requested page = -1 indicates the last page
        if requested_page > -1:
            skip = requested_page * limit
        else:
            nr_of_pages, _ = divmod(total_rows, limit)
            skip = nr_of_pages * limit

        pools_for_status = last_payday.pool_status_for_bakers[status]
        enhanced_pools = await get_pools(
            mongodb, mongomotor, pools_for_status, last_payday
        )
        reverse = True if direction == "descending" else False
        sorted_pool_ids = []
        if key in ["d30", "d90", "d180"]:
            sorted_pool_ids = sorted(
                enhanced_pools,
                key=lambda x: (enhanced_pools[x][key]["apy"]),
                reverse=reverse,
            )
        elif key in [
            "block_commission_rate",
            "tx_commission_rate",
            "expectation",
            "delegated_percentage",
        ]:
            sorted_pool_ids = sorted(
                enhanced_pools, key=lambda x: (enhanced_pools[x][key]), reverse=reverse
            )

        sorted_pools = [enhanced_pools[x] for x in sorted_pool_ids]

        html = process_sorted_pools_to_HTML_v2(
            sorted_pools[skip : (skip + limit)],
            status,
            key,
            direction,
            requested_page,
            len(sorted_pools),
        )

        html += transactions_html_footer()
        return html


@router.get(
    "/ajax_passive_delegators_html_v2/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_passive_delegators_html_v2(
    request: Request,
    requested_page: int,
    total_rows: int,
    api_key: str,
    recurring: Recurring = Depends(get_recurring),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tags: dict = Depends(get_labeled_accounts),
):
    limit = 20
    user: UserV2 = get_user_detailsv2(request)

    if api_key != request.app.env["API_KEY"]:
        return "No valid api key supplied."
    else:
        if requested_page > -1:
            skip = requested_page * limit
        else:
            nr_of_pages, _ = divmod(total_rows, limit)
            skip = nr_of_pages * limit

        delegators_current_payday = [
            x
            for x in grpcclient.get_delegators_for_passive_delegation_in_reward_period(
                "last_final"
            )
        ]
        delegators_in_block = [
            x for x in grpcclient.get_delegators_for_passive_delegation("last_final")
        ]

        delegators_current_payday_list = set(
            [x.account for x in delegators_current_payday]
        )

        delegators_in_block_list = set([x.account for x in delegators_in_block])

        delegators_current_payday_dict = {
            x.account: x for x in delegators_current_payday
        }
        delegators_in_block_dict = {x.account: x for x in delegators_in_block}

        new_delegators = delegators_in_block_list - delegators_current_payday_list

        # delegators_in_block_list = list(delegators_in_block_list)
        new_delegators_dict = {x: delegators_in_block_dict[x] for x in new_delegators}

        delegators = sorted(
            delegators_current_payday, key=lambda x: x.stake, reverse=True
        )

        html = process_passive_delegators_to_HTML_v2(
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
