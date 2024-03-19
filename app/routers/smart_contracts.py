# ruff: noqa: F403, F405, E402, E501, E722

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse

from app.classes.dressingroom import MakeUp, TransactionClassifier, MakeUpRequest
from dateutil.relativedelta import relativedelta
from datetime import timedelta
from ccdefundamentals.GRPCClient import GRPCClient

from sortedcontainers import SortedDict
from app.Recurring.recurring import Recurring
from app.jinja2_helpers import *
from pymongo import DESCENDING
from ccdefundamentals.GRPCClient.CCD_Types import *
from env import *
from app.state.state import *
from pydantic import BaseModel
from ccdefundamentals.tooter import Tooter, TooterType, TooterChannel
from ccdefundamentals.mongodb import (
    MongoDB,
    Collections,
    MongoTypeModule,
    MongoTypeInstance,
    MongoMotor,
)
from bisect import bisect_right
from app.ajax_helpers import (
    process_transactions_to_HTML,
    transactions_html_footer,
    mongo_transactions_html_header,
)
import collections


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

    result = list(
        db_to_use[Collections.blocks_per_day].find(
            filter={},
            projection={
                "_id": 0,
                "date": 1,
                "height_for_last_block": 1,
                "slot_time_for_last_block": 1,
            },
        )
    )
    print(f"Count #txs = {len(result)}")
    block_end_of_day_dict = {x["height_for_last_block"]: x["date"] for x in result}
    heights = list(block_end_of_day_dict.keys())

    module_name = MongoTypeModule(
        **db_to_use[Collections.modules].find_one({"_id": source_module})
    ).module_name

    result = list(
        db_to_use[Collections.involved_contracts].find(
            filter={"source_module": source_module},
            projection={"_id": 0, "block_height": 1},
        )
    )
    block_heights_for_contract_transactions = [x["block_height"] for x in result]
    days = [
        find_date_for_height(heights, block_end_of_day_dict, x)
        for x in block_heights_for_contract_transactions
    ]
    counter = dict(collections.Counter(days))
    # print (counter)
    df = pd.DataFrame.from_dict(counter, orient="index").reset_index()
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

    df["transaction_cumsum"] = df["transaction_count"].cumsum()
    # df.head()
    # limit = 60

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

    cumsum = (
        alt.Chart(df)
        .mark_area(
            color="lightblue",
            # interpolate='step-after',
            line=True,
        )
        .encode(x="date:T", y="transaction_cumsum")
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

    result = list(
        db_to_use[Collections.blocks_per_day].find(
            filter={},
            projection={
                "_id": 0,
                "date": 1,
                "height_for_last_block": 1,
                "slot_time_for_last_block": 1,
            },
        )
    )
    print(f"Count #txs = {len(result)}")
    block_end_of_day_dict = {x["height_for_last_block"]: x["date"] for x in result}
    heights = list(block_end_of_day_dict.keys())

    module_names = [
        MongoTypeModule(**x).module_name
        for x in db_to_use[Collections.modules].find(
            {"_id": {"$in": reporting_request.source_modules}}
        )
    ]
    modules_dict = {
        MongoTypeModule(**x).id: MongoTypeModule(**x)
        for x in db_to_use[Collections.modules].find()
    }
    result = list(
        db_to_use[Collections.involved_contracts].find(
            filter={"source_module": {"$in": reporting_request.source_modules}},
            projection={"_id": 0, "block_height": 1, "source_module": 1},
        )
    )

    for r in result:
        r.update(
            {
                "display_name": f'{r["source_module"][:4]} | {modules_dict[r["source_module"]].module_name}',
                "date": dateutil.parser.parse(
                    find_date_for_height(
                        heights, block_end_of_day_dict, r["block_height"]
                    )
                ),
            }
        )

    df = pd.DataFrame(result)
    df_group = (
        df.groupby(
            [
                "source_module",
                "display_name",
                pd.Grouper(key="date", freq=reporting_request.period),
            ]
        )
        .count()
        .reset_index()
    )

    df_group_all = (
        df.groupby([pd.Grouper(key="date", freq=reporting_request.period)])
        .count()
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
        next_month = end_of_day.replace(day=28) + timedelta(days=4)
        res = next_month - timedelta(days=next_month.day)
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
    tooter.send(
        channel=TooterChannel.NOTIFIER,
        message=f"{user_string(user)} visited /smart-contracts/usage.",
        notifier_type=TooterType.INFO,
    )
    print(f"{module=}")
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
    tooter.send(
        channel=TooterChannel.NOTIFIER,
        message=f"{user_string(user)} visited /smart-contracts/reporting.",
        notifier_type=TooterType.INFO,
    )
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

    tooter.send(
        channel=TooterChannel.NOTIFIER,
        message=f"{user_string(user)} visited /smart-contracts/usage.",
        notifier_type=TooterType.INFO,
    )

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
    if result:
        module = MongoTypeModule(**result)

    else:
        module = None

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
    contracts_with_tag_info: dict = Depends(get_contracts_with_tag_info),
    tags: dict = Depends(get_labeled_accounts),
    # token_addresses_with_markup: dict = Depends(get_token_addresses_with_markup),
    credential_issuers: list = Depends(get_credential_issuers),
    ccd_historical: dict = Depends(get_exchange_rates_ccd_historical),
):
    limit = 20
    instance_address = f"<{instance_index},{instance_subindex}>"
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet

    tx_tabs: dict[TransactionClassifier, list] = {}
    tx_tabs_active: dict[TransactionClassifier, bool] = {}

    for tab in TransactionClassifier:
        tx_tabs[tab] = []

    txs_hashes = [
        x["tx_hash"]
        for x in db_to_use[Collections.impacted_addresses].find(
            {"impacted_address_canonical": instance_address}
            # {"contract": instance_address}
        )
    ]

    # requested page = 0 indicated the first page
    # requested page = -1 indicates the last page
    if requested_page > -1:
        skip = requested_page * limit
    else:
        nr_of_pages, _ = divmod(total_rows, limit)
        skip = nr_of_pages * limit

    tx_result = [
        CCD_BlockItemSummary(**x)
        for x in db_to_use[Collections.transactions]
        .find({"_id": {"$in": txs_hashes}})
        .skip(skip)
        .limit(limit)
        .sort("block_info.height", DESCENDING)
    ]

    if len(txs_hashes) > 0:
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
        len(txs_hashes),
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
            "net": net,
        },
    )


@router.get("/{net}/instance/{instance_index}/{subindex}")  # type:ignore
async def smart_contract_instance(
    request: Request,
    net: str,
    instance_index: int,
    subindex: int,
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tags: dict = Depends(get_labeled_accounts),
    contracts_with_tag_info: dict = Depends(get_contracts_with_tag_info),
):
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    instance_address = f"<{instance_index},{subindex}>"

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
