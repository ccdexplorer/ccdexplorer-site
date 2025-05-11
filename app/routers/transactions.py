# ruff: noqa: F403, F405, E402, E501, E722, F401

import csv
import datetime as dt
import uuid
import pandas as pd
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import *
from ccdexplorer_fundamentals.mongodb import (
    Collections,
    MongoDB,
    MongoMotor,
    MongoTypeBlockPerDay,
)
from ccdexplorer_fundamentals.tooter import Tooter, TooterChannel, TooterType
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, FileResponse
from rich import print

from app.ajax_helpers import (
    mongo_transactions_html_header,
    process_transactions_to_HTML,
    transactions_html_footer,
)
from app.classes.dressingroom import MakeUp, MakeUpRequest, TransactionClassifier
from app.env import *
from app.jinja2_helpers import *
from app.Recurring.recurring import Recurring
from app.state.state import get_mongo_db, get_mongo_motor, get_user_detailsv2
from app.utils import user_string

router = APIRouter()


def get_all_data_for_analysis_and_project(
    analysis: str, project_id: str, mongodb: MongoDB, dates_to_include: list[str]
) -> list[str]:
    pipeline = [
        {"$match": {"date": {"$in": dates_to_include}}},
        {"$match": {"type": analysis}},
        {"$match": {"project": project_id}},
        {"$project": {"_id": 0, "type": 0, "usecase": 0}},
        {"$sort": {"date": 1}},
    ]
    result = mongodb.mainnet[Collections.statistics].aggregate(pipeline)
    return [x for x in result]


def get_all_usecases(mongodb: MongoDB) -> list[str]:
    return {
        x["_id"]: x["display_name"]
        for x in mongodb.utilities[CollectionsUtilities.usecases].find()
    }


def get_all_projects(mongodb: MongoDB) -> list[str]:
    return {
        x["_id"]: x["display_name"]
        for x in mongodb.utilities[CollectionsUtilities.projects].find()
    }


class TXCountReportingRequest(BaseModel):
    net: str
    start_date: str
    end_date: str
    usecase_id: str
    group_by: str
    tx_types: list


@router.post(
    "/ajax_transaction_types_reporting/",
    response_class=HTMLResponse,
)
async def ajax_transaction_types_reporting(
    request: Request,
    reporting_request: TXCountReportingRequest,
    mongodb: MongoDB = Depends(get_mongo_db),
    recurring: Recurring = Depends(get_recurring),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
):
    net = reporting_request.net

    dates_to_include = generate_dates_from_start_until_end(
        reporting_request.start_date, reporting_request.end_date
    )
    all_data = get_all_data_for_analysis_and_project(
        "statistics_transaction_types",
        reporting_request.usecase_id,
        mongodb,
        dates_to_include,
    )
    df = pd.json_normalize(all_data)
    # only continue if we have data
    if len(df) > 0:
        # make sure we can sum up values
        df.fillna(0)
        # as we can have more than 1 address per usecase, we need to
        # groupby date.
        df_group = df.groupby("date").sum().reset_index()
        df_group["date"] = pd.to_datetime(df_group["date"])
        # address not needed anymore
        if "address" in df_group.columns:
            df_group.drop(["address"], axis=1, inplace=True)
        # this removes the table name prefix
        cols = [x.replace("tx_type_counts.", "") for x in df_group.columns]
        df_group.columns = cols

        # now we are ready to only work with selected columns
        if reporting_request.tx_types != ["all"]:
            cols = set(df_group.columns) - set(["date"])
            cols_to_drop = cols - set(reporting_request.tx_types)
            df_group.drop(cols_to_drop, axis=1, inplace=True)

            # df_group.drop(
            #     ["last_block_processed", "based_on_addresses"], axis=1, inplace=True
            # )
        # now ready to add a totals column for succesfull txs
        success_columns = list(
            (
                set(CCD_AccountTransactionEffects.model_fields.keys())
                - set(["none", "date"])
            )
            & set(df_group.columns)
        )
        rejected_columns = list(
            (set(CCD_RejectReason.model_fields.keys()) - set(["date"]))
            & set(df_group.columns)
        )
        # cols = list(set(df_group.columns) - set(["date"]))
        # df_group["total_success_count"] = df_group[success_columns].sum(axis=1)
        df_group["tx_rejected"] = df_group[rejected_columns].sum(axis=1)
        df_group["total_tx_count"] = df_group[success_columns].sum(axis=1) + df_group[
            rejected_columns
        ].sum(axis=1)

        df_group.drop(rejected_columns, axis=1, inplace=True)

        if reporting_request.group_by == "Daily":
            letter = "D"
            tooltip = "Day"
        if reporting_request.group_by == "Weekly":
            letter = "W"
            tooltip = "Week"
        if reporting_request.group_by == "Monthly":
            letter = "ME"
            tooltip = "Month"

        df_grouped = (
            df_group.groupby([pd.Grouper(key="date", axis=0, freq=letter)])
            .sum()
            .reset_index()
        )
        df_grouped.sort_values(by="date", ascending=False, inplace=True)
        df_grouped["date"] = df_grouped["date"].dt.strftime("%Y-%m-%d")
        # return df_grouped.to_dict("records")
        records = df_grouped.to_dict("records")
        filename = f"/tmp/transactions count - {dt.datetime.now():%Y-%m-%d %H-%M-%S} for {reporting_request.usecase_id} grouped {reporting_request.group_by.lower()} - {uuid.uuid4()}.csv"
        if "based_on_addresses" in df_grouped.columns:
            df_grouped.drop("based_on_addresses", axis=1, inplace=True)
        if "last_block_processed" in df_grouped.columns:
            df_grouped.drop("last_block_processed", axis=1, inplace=True)
        df_grouped.to_csv(filename, index=False)

    else:
        records = []
    html = templates.get_template(
        "/transactions_search/transaction_count_table.html"
    ).render(
        {
            "env": request.app.env,
            "net": net,
            "request": request,
            "records": records,
            "reporting_request": reporting_request,
            "type": reporting_request.group_by,
            "filename": filename,
        },
    )
    return html


@router.get("/{net}/transactions-search", response_class=HTMLResponse)
async def transactions_search(
    request: Request,
    net: str,
):
    user: UserV2 = await get_user_detailsv2(request)
    return templates.TemplateResponse(
        "transactions_search/start.html",
        {"request": request, "env": request.app.env, "user": user, "net": net},
    )
