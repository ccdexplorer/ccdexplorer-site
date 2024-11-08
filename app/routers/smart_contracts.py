# ruff: noqa: F403, F405, E402, E501, E722

# import collections
from bisect import bisect_right
import numpy as np
from datetime import timedelta
import plotly.express as px
import json
import base64
import uuid
from app.classes.dressingroom import (
    MakeUp,
    MakeUpRequest,
    RequestingRoute,
)
from ccdexplorer_fundamentals.cis import StandardIdentifiers, MongoTypeTokensTag
import pandas as pd
from ccdexplorer_fundamentals.GRPCClient.types_pb2 import VersionedModuleSource
from ccdexplorer_schema_parser.Schema import Schema

# from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import *
from ccdexplorer_fundamentals.mongodb import (
    Collections,
    # MongoDB,
    # MongoMotor,
    MongoTypeInstance,
    MongoTypeModule,
)
from ccdexplorer_fundamentals.tooter import Tooter  # , TooterChannel, TooterType
from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from pymongo import DESCENDING
from sortedcontainers import SortedDict

# from app.ajax_helpers import (
#     mongo_transactions_html_header,
#     process_transactions_to_HTML,
#     transactions_html_footer,
# )
from app.classes.dressingroom import MakeUp, MakeUpRequest, TransactionClassifier
from app.env import *
from app.jinja2_helpers import *
from app.state import get_httpx_client, get_labeled_accounts, get_user_detailsv2

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


@router.post(
    "/{net}/module/{module_ref}/usage",
    response_class=HTMLResponse,
)
async def request_ajax_source_module(
    request: Request,
    net: str,
    module_ref: str,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    theme = "dark"
    body = await request.body()
    if body:
        theme = body.decode("utf-8").split("=")[1]
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/module/{module_ref}/usage",
        httpx_client,
    )
    result = api_result.return_value if api_result.ok else []
    if len(result) == 0:
        return None

    df = pd.DataFrame(result)

    df.columns = ["date", "transaction_count"]
    df["date"] = pd.to_datetime(df["date"])
    rng = [
        "#AE7CF7",
        "#70B785",
        "#6E97F7",
    ]
    fig = px.bar(
        df,
        x="date",
        y="transaction_count",
        color_discrete_sequence=rng,
        # range_x=["2021-06-09", f"{dt.datetime.now().astimezone(dt.UTC):%Y-%m-%d}"],
        template=ccdexplorer_plotly_template(theme),
    )
    fig.update_yaxes(
        title_text=None,
        showgrid=False,
        linewidth=0,
        zerolinecolor="rgba(0,0,0,0)",
    )
    # fig.update_traces(mode="lines")
    fig.update_xaxes(
        title=None,
        type="date",
        showgrid=False,
        linewidth=0,
        zerolinecolor="rgba(0,0,0,0)",
    )
    fig.update_layout(
        height=250,
        # width=320,
        legend_y=-0.25,
        title="Module usage",
        # title_y=0.46,
        legend=dict(orientation="h"),
        # legend_x=0.7,
        margin=dict(l=0, r=0, t=0, b=0),
    )

    html = fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )

    return html


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
        if row:
            flat_list.extend(row)
    return flat_list


@router.post(
    "/ajax_source_module_reporting/",
    response_class=HTMLResponse,
)
async def ajax_source_module_reporting(
    request: Request,
    reporting_request: ReportingRequest,
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
    source_to_name = {x.id: f"{x.id[:4]}-{x.module_name}" for x in module_classes}
    instance_to_source = {}
    for module_class in module_classes:
        module_instances = list(
            db_to_use[Collections.instances].find({"source_module": module_class.id})
        )
        for instance in module_instances:
            instance_to_source[instance["_id"]] = module_class.id
    modules_instances = list(instance_to_source.keys())
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
    if len(result) > 0:
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
    else:
        dict_to_send = {}
        results_all = {}
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


@router.get("/ajax_modules/{net}/{year}{month}")  # type:ignore
async def smart_contracts(
    request: Request,
    net: str,
    year: int,
    month: int,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/modules/{year}/{month}",
        httpx_client,
    )
    modules_to_show = api_result.return_value if api_result.ok else None


@router.get("/{net}/smart-contracts")  # type:ignore
async def smart_contracts(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/modules/{module_ref}/instances/{skip}/{limit}",
        httpx_client,
    )
    instances_result = api_result.return_value if api_result.ok else None
    return templates.TemplateResponse(
        "smart_contracts/smart_contracts.html",
        {
            "env": request.app.env,
            "request": request,
            "net": net,
            "modules": the_dict,
            "all_instances": all_instances,
            "user": user,
            "tags": tags,
        },
    )


@router.get("/{net}/smart-contracts/usage/{module}")  # type:ignore
async def smart_contracts(
    request: Request,
    net: str,
    module: str,
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
async def smart_contracts_usage(
    request: Request,
    net: str,
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


@router.get(
    "/module_instances/{net}/{module_ref}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def get_module_instances(
    request: Request,
    net: str,
    module_ref: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
    tags: dict = Depends(get_labeled_accounts),
):
    limit = 10
    user: UserV2 = await get_user_detailsv2(request)

    if api_key != request.app.env["API_KEY"]:
        return "No valid api key supplied."
    else:
        skip = calculate_skip(requested_page, total_rows, limit)
        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/module/{module_ref}/instances/{skip}/{limit}",
            httpx_client,
        )
        instances_result = api_result.return_value if api_result.ok else None
        if not instances_result:
            error = f"Request error getting instances for module {module_ref} on {net}."
            return templates.TemplateResponse(
                "base/error-request.html",
                {
                    "request": request,
                    "error": error,
                    "env": environment,
                    "net": net,
                },
            )
        module_instances = instances_result["module_instances"]
        total_rows = instances_result["instances_count"]

        pagination_request = PaginationRequest(
            total_txs=total_rows,
            requested_page=requested_page,
            word="instance",
            action_string="instance",
            limit=limit,
        )
        pagination = pagination_calculator(pagination_request)
        html = templates.get_template(
            "smart_contracts/smart_module_instances.html"
        ).render(
            {
                "module_instances": module_instances,
                "tags": tags,
                "net": net,
                "request": request,
                "pagination": pagination,
                "totals_in_pagination": True,
                "total_rows": total_rows,
            }
        )

        return html


@router.get("/{net}/module/{module_ref}")  # type:ignore
async def module_module_address(
    request: Request,
    net: str,
    module_ref: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    request.state.api_calls = {}
    user: UserV2 = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/module/{module_ref}",
        httpx_client,
    )
    result = api_result.return_value if api_result.ok else None

    schema_available = False
    schema_dict = {}
    schema_methods = {}
    if not result:
        error = f"Can't find the module at {module_ref} on {net}."
        return templates.TemplateResponse(
            "base/error.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )
    module = MongoTypeModule(**result)
    module_name = module.module_name
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/module/{module_ref}/deployed", httpx_client
    )
    tx_deployed = (
        CCD_BlockItemSummary(**api_result.return_value) if api_result.ok else None
    )
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/module/{module_ref}/schema", httpx_client
    )
    schema_result: Schema | None = api_result.return_value if api_result.ok else None

    encoded = schema_result["module_source"]
    version = schema_result["version"]
    if version == "v1":
        ms = VersionedModuleSource()
        ms.v1.value = base64.decodebytes(json.loads(encoded).encode())
        schema = Schema(ms.v1.value, 1)
    else:
        ms = VersionedModuleSource()
        ms.v0.value = base64.decodebytes(json.loads(encoded).encode())
        schema = Schema(ms.v0.value, 0)
    if schema:
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
        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/module/{module_ref}/instances/0/1",
            httpx_client,
        )
        module_instances_result: list[str] | None = (
            api_result.return_value if api_result.ok else {"instances_count": 0}
        )
        module_instance_count = module_instances_result["instances_count"]

    # else:
    #     module = None
    #     module_instances_result = None
    #     module_instance_count = 0
    #     schema_dict = {}
    #     schema_methods = {}
    #     tx_deployed = None

    error = None
    if not module:
        error = {
            "error": True,
            "errorMessage": f"No module on {net} found at {module_ref}.",
        }
    request.state.api_calls["Module Info"] = (
        f"{request.app.api_url}/docs#/Module/get_module_v2__net__module__module_ref__get"
    )
    request.state.api_calls["Deployed Tx"] = (
        f"{request.app.api_url}/docs#/Module/get_module_deployment_tx_v2__net__module__module_ref__deployed_get"
    )
    request.state.api_calls["Module Schema"] = (
        f"{request.app.api_url}/docs#/Module/get_module_schema_v2__net__module__module_ref__schema_get"
    )
    request.state.api_calls["Module Instances"] = (
        f"{request.app.api_url}/docs#/Module/get_module_instances_v2__net__module__module_ref__instances__skip___limit__get"
    )
    request.state.api_calls["Module Usage"] = (
        f"{request.app.api_url}/docs#/Module/get_module_usage_v2__net__module__module_ref__usage_get"
    )
    return templates.TemplateResponse(
        "smart_contracts/smart_module.html",
        {
            "env": request.app.env,
            "net": net,
            "request": request,
            "tx_deployed": tx_deployed,
            "module_ref": module_ref,
            "error": error,
            "module": module,
            "module_instance_count": module_instance_count,
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
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    limit = 10
    user: UserV2 = await get_user_detailsv2(request)
    instance_address = f"<{instance_index},{instance_subindex}>"

    if api_key != request.app.env["API_KEY"]:
        return "No valid api key supplied."
    else:
        skip = calculate_skip(requested_page, total_rows, limit)
        # note we are using the account api here, as it's also valid for instances.
        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/account/{instance_address}/transactions/{skip}/{limit}",
            httpx_client,
        )
        tx_result = api_result.return_value if api_result.ok else None
        if not tx_result:
            error = f"Request error getting transactions for contract at {instance_address} on {net}."
            return templates.TemplateResponse(
                "base/error-request.html",
                {
                    "request": request,
                    "error": error,
                    "env": environment,
                    "net": net,
                },
            )

        tx_result_transactions = tx_result["transactions"]
        total_rows = tx_result["total_tx_count"]
        made_up_txs = []
        if len(tx_result_transactions) > 0:
            for transaction in tx_result_transactions:
                transaction = CCD_BlockItemSummary(**transaction)
                makeup_request = MakeUpRequest(
                    **{
                        "net": net,
                        "httpx_client": httpx_client,
                        "tags": tags,
                        "user": user,
                        "app": request.app,
                        "requesting_route": RequestingRoute.account,
                    }
                )

                classified_tx = await MakeUp(
                    makeup_request=makeup_request
                ).prepare_for_display(transaction, "", False)
                made_up_txs.append(classified_tx)

        pagination_request = PaginationRequest(
            total_txs=total_rows,
            requested_page=requested_page,
            word="tx",
            action_string="tx",
            limit=limit,
        )
        pagination = pagination_calculator(pagination_request)
        html = templates.get_template("account/account_transactions.html").render(
            {
                "transactions": made_up_txs,
                "tags": tags,
                "net": net,
                "request": request,
                "pagination": pagination,
                "totals_in_pagination": True,
                "total_rows": total_rows,
            }
        )

        return html


# @router.get("/{net}/instance/{instance_address}")  # type:ignore
# async def smart_contract_instance_full_address(
#     request: Request,
#     net: str,
#     instance_address: str,
#     tags: dict = Depends(get_labeled_accounts),
# ):
#     user: UserV2 = get_user_detailsv2(request)
#     db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet

#     result = db_to_use[Collections.instances].find_one({"_id": instance_address})
#     if result:
#         contract = MongoTypeInstance(**result)
#     else:
#         contract = None

#     error = None
#     if not contract:
#         error = {
#             "error": True,
#             "errorMessage": f"No instance found at {instance_address}.",
#         }

#     return templates.TemplateResponse(
#         "smart_contracts/smart_instance.html",
#         {
#             "env": request.app.env,
#             "net": net,
#             "request": request,
#             "error": error,
#             "contract": contract,
#             "user": user,
#             "tags": tags,
#         },
#     )


@router.get(
    "/ajax_track_item_id/{net}/{instance_index}/{subindex}/{item_id}",
    response_class=HTMLResponse,
)  # type:ignore
async def ajax_track_item_id(
    request: Request,
    net: str,
    instance_index: int,
    subindex: int,
    item_id: str,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/contract/{instance_index}/{subindex}/tnt/logged-events/{item_id}",
        httpx_client,
    )
    item_id_statuses = api_result.return_value if api_result.ok else []
    html = templates.get_template("smart_contracts/tnt_logged_events.html").render(
        {
            "logged_events": item_id_statuses,
            "net": net,
            "env": request.app.env,
            "request": request,
        }
    )

    return html


@router.get("/{net}/instance/{instance_index}/{subindex}")
async def smart_contract_instance(
    request: Request,
    net: str,
    instance_index: int,
    subindex: int,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    request.state.api_calls = {}
    user: UserV2 = await get_user_detailsv2(request)
    instance_address = f"<{instance_index},{subindex}>"
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/contract/{instance_index}/{subindex}/supports-cis-standard/CIS-6",
        httpx_client,
    )
    if api_result.ok:
        supports_cis6 = api_result.return_value
        if supports_cis6:
            api_result = await get_url_from_api(
                f"{request.app.api_url}/v2/{net}/contract/{instance_index}/{subindex}/tnt/ids",
                httpx_client,
            )
            item_ids = api_result.return_value if api_result.ok else []

            api_result = await get_url_from_api(
                f"{request.app.api_url}/v2/{net}/contract/{instance_index}/{subindex}/tnt/logged-events",
                httpx_client,
            )
            all_logged_events = api_result.return_value if api_result.ok else []

            filename = events_to_file(instance_address, all_logged_events)
        else:
            item_ids = None
            filename = None

        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/contract/{instance_index}/{subindex}/tokens-available",
            httpx_client,
        )
        tokens_available = api_result.return_value if api_result.ok else False

        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/contract/{instance_index}/{subindex}/info",
            httpx_client,
        )
        contract = (
            MongoTypeInstance(**api_result.return_value) if api_result.ok else None
        )

        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/contract/{instance_index}/{subindex}/tag-info",
            httpx_client,
        )
        tag_information = (
            MongoTypeTokensTag(**api_result.return_value) if api_result.ok else None
        )
        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/contract/{instance_index}/{subindex}/deployed",
            httpx_client,
        )
        tx_deployed = (
            CCD_BlockItemSummary(**api_result.return_value) if api_result.ok else None
        )

        request.state.api_calls["Instance Info"] = (
            f"{request.app.api_url}/docs#/Contract/get_instance_information_v2__net__contract__contract_index___contract_subindex__info_get"
        )
        request.state.api_calls["Verified Information"] = (
            f"{request.app.api_url}/docs#/Contract/get_instance_tag_information_v2__net__contract__contract_index___contract_subindex__tag_info_get"
        )
        request.state.api_calls["Tokens Available"] = (
            f"{request.app.api_url}/docs#/Contract/get_contract_tokens_available_v2__net__contract__contract_index___contract_subindex__tokens_available_get"
        )
        request.state.api_calls["Deployed Tx"] = (
            f"{request.app.api_url}/docs#/Contract/get_contract_deployment_tx_v2__net__contract__contract_index___contract_subindex__deployed_get"
        )
        request.state.api_calls["Instance Transactions"] = (
            f"{request.app.api_url}/docs#/Account/get_account_txs_v2__net__account__account_id__transactions__skip___limit__get"
        )
        request.state.api_calls["Token Information"] = (
            f"{request.app.api_url}/docs#/Contract/get_token_information_v2__net__contract__contract_index___contract_subindex__token_information_get"
        )
        request.state.api_calls["Schema from Source"] = (
            f"{request.app.api_url}/docs#/Contract/get_schema_from_source_v2__net__contract__contract_index___contract_subindex__schema_from_source_get"
        )
        if contract:
            error = None
            # dressed_up_contract = contracts_with_tag_info.get(contract.id)
            return templates.TemplateResponse(
                "smart_contracts/smart_instance.html",
                {
                    "env": request.app.env,
                    "request": request,
                    "error": error,
                    "tx_deployed": tx_deployed,
                    "tokens_available": tokens_available,
                    "contract": contract,
                    "index": instance_index,
                    "subindex": subindex,
                    "tag_information": tag_information,
                    "user": user,
                    "tags": tags,
                    "net": net,
                    "supports_cis6": supports_cis6,
                    "item_ids": item_ids,
                    "filename": filename,
                },
            )
    # api_result NOT ok
    else:
        if api_result.status_code == 404:
            error = {
                "error": True,
                "errorMessage": f"No instance found on {net} for {instance_address}.",
            }
        else:
            error = {
                "error": True,
                "errorMessage": f"Error getting info on {net} for {instance_address}.",
            }
        contract = None
        return templates.TemplateResponse(
            "smart_contracts/smart_instance.html",
            {
                "env": request.app.env,
                "net": net,
                "request": request,
                "error": error,
            },
        )


def events_to_file(instance_address: str, all_logged_events: list):
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
    return filename
