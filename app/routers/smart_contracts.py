# ruff: noqa: F403, F405, E402, E501, E722
import os
import subprocess
from bisect import bisect_right

import aiofiles
import numpy as np
import uuid
import altair as alt
from ccdexplorer_fundamentals.cis import StandardIdentifiers
import pandas as pd
from ccdexplorer_fundamentals.GRPCClient.types_pb2 import VersionedModuleSource
from ccdexplorer_schema_parser.Schema import Schema

from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import *
from ccdexplorer_fundamentals.mongodb import (
    Collections,
    MongoDB,
    MongoMotor,
    MongoTypeInstance,
    MongoTypeModule,
)
from ccdexplorer_fundamentals.tooter import Tooter, TooterChannel, TooterType
from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from pymongo import DESCENDING
from sortedcontainers import SortedDict

from app.ajax_helpers import (
    mongo_transactions_html_header,
    process_transactions_to_HTML,
    transactions_html_footer,
)
from app.classes.dressingroom import MakeUp, MakeUpRequest, TransactionClassifier
from app.env import *
from app.jinja2_helpers import *
from app.Recurring.recurring import Recurring
from app.state.state import *

router = APIRouter()


# NET = 'mainnet'
# db = mongodb.mainnet if NET == 'mainnet' else mongodb.testnet
def find_date_for_height(heights, block_end_of_day_dict, height):
    found_index = bisect_right(heights, height)
    # meaning it's today...
    if found_index == len(heights):
        return f"{dt.datetime.now():%Y-%m-%d}"
    else:
        return block_end_of_day_dict[heights[found_index]]


@router.get("/instance/{instance_index}/{subindex}", response_class=RedirectResponse)
async def redirect_instance_to_mainnet(
    request: Request, instance_index: int, subindex: int, net="mainnet"
):
    if net == "testnet":
        response = RedirectResponse(
            url=f"/testnet/instance/{instance_index}/{subindex}", status_code=302
        )
    else:
        response = RedirectResponse(
            url=f"/mainnet/instance/{instance_index}/{subindex}", status_code=302
        )
    return response


@router.get(
    "/ajax_source_module/{net}/{source_module}/{days}/{width}",
    response_class=HTMLResponse,
)
async def request_ajax_source_module(
    request: Request,
    net: str,
    source_module: str,
    days: int,
    width: int,
    mongodb: MongoDB = Depends(get_mongo_db),
    recurring: Recurring = Depends(get_recurring),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet

    module_class = MongoTypeModule(
        **db_to_use[Collections.modules].find_one({"_id": source_module})
    )
    module_name = module_class.module_name
    modules_instances = module_class.contracts
    if modules_instances:
        pipeline = [
            {"$match": {"impacted_address_canonical": {"$in": modules_instances}}},
            {"$group": {"_id": "$date", "count": {"$sum": 1}}},
        ]
        result = list(db_to_use[Collections.impacted_addresses].aggregate(pipeline))
    else:
        result = []
    if len(result) == 0:
        return None

    df = pd.DataFrame(result)
    days_alive = (
        dt.datetime.now() - dt.datetime(2021, 6, 9, 10, 0, 0)
    ).total_seconds() / (60 * 60 * 24)
    domain_pd = pd.to_datetime(
        [
            dt.date(2021, 6, 9) + dt.timedelta(days=x)
            for x in range(0, int(days_alive + 1))
        ]
    )

    df.columns = ["date", "transaction_count"]
    df["date"] = pd.to_datetime(df["date"])

    line = (
        alt.Chart(df)
        .mark_bar(
            color="lightblue",
            # interpolate='step-after',
            line=True,
        )
        .encode(
            x=alt.X("date:T", scale=alt.Scale(domain=list(domain_pd))),
            y="transaction_count",
        )
    )

    chart = (
        (line)
        .resolve_scale(y="independent")
        .properties(width=width * 0.80 if width < 400 else width, title=module_name)
    )
    return chart.to_json(format="vega")


class ReportingRequest(BaseModel):
    net: str
    source_modules: list
    period: str  # Enum


class ReportingPeriods(Enum):
    W1 = "1W"
    M1 = "1M"


def flatten_extend(matrix):
    flat_list = []
    for row in matrix:
        flat_list.extend(row)
    return flat_list


@router.post(
    "/ajax_source_module_reporting/",
    response_class=HTMLResponse,
)
async def ajax_source_module_reporting(
    request: Request,
    reporting_request: ReportingRequest,
    mongodb: MongoDB = Depends(get_mongo_db),
    recurring: Recurring = Depends(get_recurring),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
):
    net = reporting_request.net
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet

    module_classes = [
        MongoTypeModule(**x)
        for x in list(
            db_to_use[Collections.modules].find(
                {"_id": {"$in": reporting_request.source_modules}}
            )
        )
    ]
    source_to_name = {x.id: x.module_name for x in module_classes}
    instance_to_source = {}
    for module_class in module_classes:
        for instance in module_class.contracts:
            instance_to_source[instance] = module_class.id
    # module_name = module_class.module_name
    modules_instances = [x.contracts for x in module_classes]
    modules_instances = flatten_extend(modules_instances)
    pipeline = [
        {"$match": {"impacted_address_canonical": {"$in": modules_instances}}},
        {
            "$group": {
                "_id": {"date": "$date", "instance": "$impacted_address_canonical"},
                "count": {"$sum": 1},
            }
        },
    ]
    result = list(db_to_use[Collections.impacted_addresses].aggregate(pipeline))
    new_result = []
    for r in result:
        source_module = instance_to_source[r["_id"]["instance"]]
        r.update({"source_module": source_module, "date": r["_id"]["date"]})
        del r["_id"]
        new_result.append(r)

    df = pd.DataFrame(new_result)
    df["date"] = pd.to_datetime(df["date"])
    df_group = (
        df.groupby(
            [
                "source_module",
                # "display_name",
                pd.Grouper(key="date", freq=reporting_request.period),
            ]
        )
        .sum()
        .reset_index()
    )

    df_group_all = (
        df.groupby([pd.Grouper(key="date", freq=reporting_request.period)])
        .sum()
        .reset_index()
    )
    results_all = df_group_all.to_dict("records")
    dict_to_send = {}
    for sm in reporting_request.source_modules:
        f = df_group["source_module"] == sm
        df_for_sm = df_group[f]
        dict_to_send[sm] = df_for_sm.to_dict("records")
        pass

    return templates.TemplateResponse(
        "smart_contracts/smart_contracts_reporting_all.html",
        {
            "env": request.app.env,
            "request": request,
            "source_to_name": source_to_name,
            "net": net,
            "results": dict_to_send,
            "results_all": results_all,
            "period": reporting_request.period,
            "user": user,
            "tags": tags,
        },
    )


@router.get("/{net}/smart-contracts")  # type:ignore
async def smart_contracts(
    request: Request,
    net: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
):
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    # modules = reversed(
    #     [MongoTypeModule(**x) for x in db_to_use[Collections.modules].find()]
    # )
    modules_dict = {
        x["_id"]: MongoTypeModule(**x) for x in db_to_use[Collections.modules].find()
    }
    mm = [
        CCD_BlockItemSummary(**x)
        for x in db_to_use[Collections.transactions].find(
            {"type.contents": "module_deployed"}
        )
    ]
    # for x in mm:
    #     print(
    #         f'{x["_id"]} : {x["account_transaction.effects.contract_initialized.origin_ref"]}'
    #     )
    inits_dict = {
        x.account_transaction.effects.module_deployed: x.block_info.slot_time
        for x in mm
    }
    # for x in db_to_use[Collections.transactions].find(
    #     {"account_transaction.effects.contract_initialized": {"$exists": True}}
    # )
    # }

    # update modules_dict with init dates
    modules_sorted_by_date = SortedDict()
    for module_ref, module in modules_dict.items():
        init_date = inits_dict.get(module_ref, None)
        if init_date:
            module.init_date = init_date
            modules_dict[module_ref] = module
            modules_sorted_by_date[init_date] = module

    # now do an ugly hack to get the modules into year/month buckets
    max_date = max(modules_sorted_by_date.keys())
    min_date = min(modules_sorted_by_date.keys())
    months_list = []
    cur_date = min_date
    while cur_date < max_date:
        end_of_day = dt.datetime.combine(cur_date, dt.time.max)
        next_month = end_of_day.replace(day=28) + dt.timedelta(days=4)
        res = next_month - dt.timedelta(days=next_month.day)
        # print(f"Last date of month is:", res.date())
        months_list.append(
            {
                "display_string": f"{cur_date.year}-{cur_date.month:02}",
                "end_of_month_date": res,
            }
        )
        cur_date += relativedelta(months=1)

    the_dict = {}
    for init_date in reversed(modules_sorted_by_date):
        display_string_for_module = f"{init_date.year}-{init_date.month:02}"
        already_found_display_dates = the_dict.get(display_string_for_module, None)
        if not already_found_display_dates:
            the_dict[display_string_for_module] = [modules_sorted_by_date[init_date]]
        else:
            the_dict[display_string_for_module].append(
                modules_sorted_by_date[init_date]
            )

    return templates.TemplateResponse(
        "smart_contracts/smart_contracts.html",
        {
            "env": request.app.env,
            "request": request,
            "net": net,
            "modules": the_dict,
            "user": user,
            "tags": tags,
        },
    )


@router.get("/{net}/smart-contracts/verification", response_class=HTMLResponse)  # type:ignore
@router.get("/{net}/smart-contracts/verification/{smart_contract_address}", response_class=HTMLResponse)
async def module_verification(
        request: Request,
        net: str,
        recurring: Recurring = Depends(get_recurring),
        mongodb: MongoDB = Depends(get_mongo_db),
        grpcclient: GRPCClient = Depends(get_grpcclient),
        tooter: Tooter = Depends(get_tooter),
        smart_contract_address: Optional[str] = None
):
    user: UserV2 = get_user_detailsv2(request)
    return templates.TemplateResponse(
        "smart_contracts/smart_module_verification.html",
        {
            "env": request.app.env,
            "request": request,
            "net": net,
            "user": user,
            "address": smart_contract_address,
            "locked" : smart_contract_address is not None
        },
    )


@router.post("/{net}/smart-contracts/verification")  # type:ignore
@router.post("/{net}/smart-contracts/verification/{smart_contract_address}")
async def module_verification_post(
        request: Request,
        net: str,
        recurring: Recurring = Depends(get_recurring),
        mongodb: MongoDB = Depends(get_mongo_db),
        grpcclient: GRPCClient = Depends(get_grpcclient),
        tooter: Tooter = Depends(get_tooter),
        smart_contract_address: Optional[str] = None
):
    from ccdexplorer_fundamentals.env import GRPC_MAINNET, GRPC_TESTNET

    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    user: UserV2 = get_user_detailsv2(request)

    if net == "testnet":
        node_address = ["--grpc-ip", GRPC_TESTNET[0].get('host'), "--grpc-port", str(GRPC_TESTNET[0].get('port'))]
    else:
        node_address = ["--grpc-ip", GRPC_MAINNET[0].get('host'), "--grpc-port", str(GRPC_MAINNET[0].get('port'))]

    body = await request.form()
    if smart_contract_address is None:
        smart_contract_address = body.get("module_address")
        if smart_contract_address:
            smart_contract_address = smart_contract_address.strip()

    smart_contract_sources = body.get("module_sources")

    upload_folder = f"./tmp/{smart_contract_address}"

    module_path = f"{upload_folder}/contract.wasm.v1"
    sources_path = f"{upload_folder}/{smart_contract_sources.filename}"

    if os.path.exists(upload_folder):
        if os.path.exists(module_path):
            os.remove(module_path)
        if os.path.exists(sources_path):
            os.remove(sources_path)
    else:
        if not os.path.exists("tmp"):
            os.mkdir("tmp")
        os.mkdir(upload_folder)

    async with aiofiles.open(sources_path, "wb") as f:
        await f.write(await UploadFile(smart_contract_sources.file).read())

    ccd_client_run = subprocess.run(
        ["./concordium-client", "module", "show", smart_contract_address, "--out", f"{module_path}"] + node_address,
        capture_output=True, text=True
    )

    if ccd_client_run.returncode == 0:
        cargo_run = subprocess.run(
            ["cargo", "concordium", "verify-build", "--module", module_path, f"--source", f"{sources_path}"],
            capture_output=True, text=True
        )
        if cargo_run.returncode == 0:
            result = {"success": True, "message": "Source and module match."}
        else:
            returned_message = cargo_run.stderr.replace("", "")
            if "Error: " in returned_message:
                returned_message = returned_message.split("error:")[-1].replace("\n", "<br>").replace("[1;31m", "").replace("[0m", "").strip()
            result = {"success": False, "message": returned_message}

        if db_to_use[Collections.modules].find_one({"_id": smart_contract_address}):
            db_to_use[Collections.modules].update_one(
                {"_id": smart_contract_address},
                {"$set": {"verification_status": result["success"], "verification_message": result["message"]}},
                upsert=True,
            )
    else:
        result = {"success": False, "message": ccd_client_run.stderr.strip()}

    if os.path.exists(module_path):
        os.remove(module_path)
    if os.path.exists(sources_path):
        os.remove(sources_path)
    os.rmdir(upload_folder)

    return templates.TemplateResponse(
        "smart_contracts/smart_module_verification.html",
        {
            "env": request.app.env,
            "request": request,
            "net": net,
            "user": user,
            "address": smart_contract_address,
            "result": result,
            "locked": smart_contract_address is not None
        },
    )


@router.get("/{net}/smart-contracts/usage/{module}")  # type:ignore
async def smart_contracts(
    request: Request,
    net: str,
    module: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
):
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    module_list = [MongoTypeModule(**x) for x in db_to_use[Collections.modules].find()]

    return templates.TemplateResponse(
        "smart_contracts/source_module_graph.html",
        {
            "env": request.app.env,
            "request": request,
            "modules": module_list,
            "user": user,
            "tags": tags,
            "net": net,
            "module": module,
        },
    )


@router.get("/{net}/smart-contracts/reporting")  # type:ignore
async def smart_contracts_reporting(
    request: Request,
    net: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
):
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    module_list = [MongoTypeModule(**x) for x in db_to_use[Collections.modules].find()]

    return templates.TemplateResponse(
        "smart_contracts/smart_contracts_reporting.html",
        {
            "env": request.app.env,
            "request": request,
            "modules": module_list,
            "reporting_periods": ReportingPeriods,
            "user": user,
            "tags": tags,
            "net": net,
        },
    )


@router.get("/{net}/smart-contracts/usage")  # type:ignore
async def smart_contracts(
    request: Request,
    net: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
):
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    module_list = [MongoTypeModule(**x) for x in db_to_use[Collections.modules].find()]

    return templates.TemplateResponse(
        "smart_contracts/source_module_graph.html",
        {
            "env": request.app.env,
            "request": request,
            "modules": module_list,
            "user": user,
            "tags": tags,
            "net": net,
        },
    )


def get_schema_from_source(
    db_to_use: dict[Collections, Collection],
    grpcclient: GRPCClient,
    net: str,
    module_ref: str,
):
    ms: VersionedModuleSource = grpcclient.get_module_source_original_classes(
        module_ref, "last_final", net=NET(net)
    )
    schema = Schema(ms.v1.value, 1) if ms.v1 else Schema(ms.v0.value, 0)

    return schema


@router.get("/{net}/module/{module_address}")  # type:ignore
async def module_module_address(
    request: Request,
    net: str,
    module_address: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
):
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    result = db_to_use[Collections.modules].find_one({"_id": module_address})
    schema_available = False
    schema_dict = {}
    schema_methods = {}
    if result:
        module = MongoTypeModule(**result)
        module_name = module.module_name
        schema = get_schema_from_source(db_to_use, grpcclient, net, module_address)
        if schema.schema:
            schema_available = True
            schema_dict["init_param"] = schema.extract_init_param_schema(module_name)
            schema_dict["init_error"] = schema.extract_init_error_schema(module_name)
            schema_dict["event"] = schema.extract_event_schema(module_name)
            for method_name in module.methods:

                schema_methods[method_name] = {
                    "receive_param": schema.extract_receive_param_schema(
                        module_name, method_name
                    ),
                    "receive_error": schema.extract_receive_error_schema(
                        module_name, method_name
                    ),
                    "receive_return": schema.extract_receive_return_value_schema(
                        module_name, method_name
                    ),
                }

    else:
        module = None

        schema_dict = {}
        schema_methods = {}

    error = None
    if not module:
        error = {
            "error": True,
            "errorMessage": f"No instance on {net} found at {module_address}.",
        }
    return templates.TemplateResponse(
        "smart_contracts/smart_module.html",
        {
            "env": request.app.env,
            "net": net,
            "request": request,
            "error": error,
            "module": module,
            "schema": schema_available,
            "schema_dict": schema_dict,
            "schema_methods": schema_methods,
            "user": user,
            "tags": tags,
        },
    )


@router.get(
    "/ajax_instance_txs_html_v2/{net}/{instance_index}/{instance_subindex}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)  # type:ignore
async def ajax_instance_txs_html_v2(
    request: Request,
    net: str,
    instance_index: int,
    instance_subindex: int,
    requested_page: int,
    total_rows: int,
    api_key: str,
    grpcclient: GRPCClient = Depends(get_grpcclient),
    mongodb: MongoDB = Depends(get_mongo_db),
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    contracts_with_tag_info_both_nets: dict = Depends(get_contracts_with_tag_info),
    tags: dict = Depends(get_labeled_accounts),
    # token_addresses_with_markup: dict = Depends(get_token_addresses_with_markup),
    credential_issuers: list = Depends(get_credential_issuers),
    ccd_historical: dict = Depends(get_exchange_rates_ccd_historical),
):
    limit = 20
    contracts_with_tag_info = contracts_with_tag_info_both_nets[NET(net)]
    instance_address = f"<{instance_index},{instance_subindex}>"
    user: UserV2 = get_user_detailsv2(request)
    # db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    db_to_use = mongomotor.testnet if net == "testnet" else mongomotor.mainnet
    tx_tabs: dict[TransactionClassifier, list] = {}
    tx_tabs_active: dict[TransactionClassifier, bool] = {}

    for tab in TransactionClassifier:
        tx_tabs[tab] = []

    # txs_hashes = [
    #     x["tx_hash"]
    #     for x in db_to_use[Collections.impacted_addresses].find(
    #         {"impacted_address_canonical": instance_address}
    #         # {"contract": instance_address}
    #     )
    # ]

    # # requested page = 0 indicated the first page
    # # requested page = -1 indicates the last page
    # if requested_page > -1:
    #     skip = requested_page * limit
    # else:
    #     nr_of_pages, _ = divmod(total_rows, limit)
    #     skip = nr_of_pages * limit

    # tx_result = [
    #     CCD_BlockItemSummary(**x)
    #     for x in db_to_use[Collections.transactions]
    #     .find({"_id": {"$in": txs_hashes}})
    #     .skip(skip)
    #     .limit(limit)
    #     .sort("block_info.height", DESCENDING)
    # ]

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
    ].find_one({"_id": instance_address})

    if not top_list_member:
        pipeline = [
            {
                "$match": {"impacted_address_canonical": {"$eq": instance_address}},
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
                "$match": {"impacted_address_canonical": {"$eq": instance_address}},
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
        None,
        total_tx_count,
        requested_page,
        tx_tabs,
        tx_tabs_active,
    )

    for tab in TransactionClassifier:
        html += process_transactions_to_HTML(
            tx_tabs[tab], tab.value, tx_tabs_active[tab], tags
        )

    html += transactions_html_footer()
    return html


@router.get("/{net}/instance/{instance_address}")  # type:ignore
async def smart_contract_instance_full_address(
    request: Request,
    net: str,
    instance_address: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tags: dict = Depends(get_labeled_accounts),
):
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet

    result = db_to_use[Collections.instances].find_one({"_id": instance_address})
    if result:
        contract = MongoTypeInstance(**result)
    else:
        contract = None

    error = None
    if not contract:
        error = {
            "error": True,
            "errorMessage": f"No instance found at {instance_address}.",
        }

    return templates.TemplateResponse(
        "smart_contracts/smart_instance.html",
        {
            "env": request.app.env,
            "net": net,
            "request": request,
            "error": error,
            "contract": contract,
            "user": user,
            "tags": tags,
        },
    )


@router.get(
    "/ajax_track_item_id/{net}/{instance_address}/{item_id}",
    response_class=HTMLResponse,
)  # type:ignore
async def ajax_track_item_id(
    request: Request,
    net: str,
    instance_address: str,
    item_id: str,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    pipeline = [
        {"$match": {"contract": instance_address}},
        {"$match": {"item_id": item_id}},
        {"$sort": {"block_height": DESCENDING}},
    ]
    item_id_statuses = list(
        db_to_use[Collections.tnt_logged_events].aggregate(pipeline)
    )
    html = templates.get_template("smart_contracts/tnt_logged_events.html").render(
        {
            "logged_events": item_id_statuses,
            "net": net,
            "env": request.app.env,
            "request": request,
        }
    )

    return html


@router.get("/{net}/instance/{instance_index}/{subindex}")  # type:ignore
async def smart_contract_instance(
    request: Request,
    net: str,
    instance_index: int,
    subindex: int,
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tags: dict = Depends(get_labeled_accounts),
    contracts_with_tag_info_both_nets: dict = Depends(get_contracts_with_tag_info),
):
    user: UserV2 = get_user_detailsv2(request)
    contracts_with_tag_info = contracts_with_tag_info_both_nets[NET(net)]
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    instance_address = f"<{instance_index},{subindex}>"
    result = db_to_use[Collections.instances].find_one({"_id": instance_address})
    if result:
        if result.get("v0"):
            module_name = result["v0"]["name"][5:]
        if result.get("v1"):
            module_name = result["v1"]["name"][5:]

        cis = CIS(
            grpcclient,
            instance_index,
            subindex,
            f"{module_name}.supports",
            NET(net),
        )
        supports_cis6 = cis.supports_standard(StandardIdentifiers.CIS_6)
        if supports_cis6:
            pipeline = [
                {
                    "$match": {"contract": instance_address},
                },
                {
                    "$group": {
                        "_id": "$item_id",
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "distinctValues": "$_id",
                    }
                },
            ]
            item_ids = [
                x["distinctValues"]
                for x in db_to_use[Collections.tnt_logged_events].aggregate(pipeline)
            ]
            pipeline_for_all = [
                {
                    "$match": {"contract": instance_address},
                },
                {
                    "$project": {
                        "_id": 0,
                        # "logged_event": 0,
                        "result": 1,
                        # "event_type": 1,
                        "contract": 1,
                        "tx_hash": 1,
                        "sender": 1,
                        "timestamp": 1,
                    }
                },
            ]
            all_logged_events = list(
                db_to_use[Collections.tnt_logged_events].aggregate(pipeline_for_all)
            )
            df = pd.json_normalize(all_logged_events)
            df.drop(
                [
                    "result.tag",
                    "result.metadata.url",
                    "result.metadata.checksum",
                    "result.additional_data",
                ],
                axis=1,
                inplace=True,
            )
            df["result.new_status"] = df["result.new_status"].fillna("")
            df["result.initial_status"] = df["result.initial_status"].fillna("")
            df["item_id"] = df["result.item_id"]
            df["status"] = np.where(
                df["result.initial_status"] == "",
                df["result.new_status"],
                df["result.initial_status"],
            )

            df.drop(
                ["result.new_status", "result.initial_status", "result.item_id"],
                axis=1,
                inplace=True,
            )
            filename = f"/tmp/track_and_trace - contract {instance_address} | {dt.datetime.now():%Y-%m-%d %H-%M-%S} - {uuid.uuid4()}.csv"
            # df_group.columns = [f"{tooltip} Ending", "Sum of Fees (CCD)"]
            df.to_csv(filename, index=False)
        else:
            item_ids = None
            filename = None

        result_list = list(
            db_to_use[Collections.tokens_links_v2].find(
                {"account_address_canonical": instance_address}
            )
        )
        if len(result_list) > 0:
            tokens_available = True
        else:
            tokens_available = False

        result = db_to_use[Collections.instances].find_one({"_id": instance_address})
        if result:
            contract = MongoTypeInstance(**result)
            index = contract.id.split(",")[0][1:]
            subindex = contract.id.split(",")[1][:-1]
            error = None
            dressed_up_contract = contracts_with_tag_info.get(contract.id)
            return templates.TemplateResponse(
                "smart_contracts/smart_instance.html",
                {
                    "env": request.app.env,
                    "request": request,
                    "error": error,
                    "tokens_available": tokens_available,
                    "contract": contract,
                    "index": index,
                    "subindex": subindex,
                    "dressed_up_contract": dressed_up_contract,
                    "user": user,
                    "tags": tags,
                    "net": net,
                    "supports_cis6": supports_cis6,
                    "item_ids": item_ids,
                    "filename": filename,
                },
            )
    else:
        error = {
            "error": True,
            "errorMessage": f"No instance found on {net} for {instance_address}.",
        }
        contract = None
        return templates.TemplateResponse(
            "smart_contracts/smart_instance.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "error": error,
                "net": net,
            },
        )
