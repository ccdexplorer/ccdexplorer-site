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
from scipy import signal
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
from app.state.state import *
from app.utils import user_string
import plotly.express as px

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


@router.get(
    "/{net}/ajax_transactions_frontpage/",
    response_class=HTMLResponse,
)
async def ajax_transactions_frontpage(
    request: Request,
    net: str,
    mongodb: MongoDB = Depends(get_mongo_db),
):

    dates_to_include = generate_dates_from_start_until_end("2024-01-01", "2024-07-16")
    all_data = get_all_data_for_analysis_and_project(
        "statistics_transaction_types",
        "all",
        mongodb,
        dates_to_include,
    )
    df = pd.json_normalize(all_data)
    df["sum_all"] = df.sum(axis=1, numeric_only=True)
    pass
    df["date"] = pd.to_datetime(df["date"])
    rng = ["#3EB7E5"]
    fig = px.scatter(
        df,
        x="date",
        y=signal.savgol_filter(
            df["sum_all"], 60, 2  # window size used for filtering
        ),  # order of fitted polynomial,
        color_discrete_sequence=rng,
        # mode="lines",
        template=ccdexplorer_plotly_template(),
        # trendline="rolling",
        # trendline_options=dict(window=12),
    )
    fig.update_yaxes(
        # secondary_y=False,
        title_text=None,
        showgrid=False,
        # autorange=False,
    )
    fig.update_traces(mode="lines")
    fig.update_xaxes(title=None, type="date", showgrid=False)
    fig.update_layout(
        # yaxis_range=[0, round(max(df["unique_impacted_address_count"]), 0) * 1.1],
        height=200,
    )
    return fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )


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


@router.get("/{net}/transactions-count", response_class=HTMLResponse)
async def request_block_node(
    request: Request,
    net: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
):
    user: UserV2 = get_user_detailsv2(request)
    all_transaction_effects = list(
        set(CCD_AccountTransactionEffects.__dict__["model_fields"].keys())
        - set(["none"])
    )
    all_projects = get_all_projects(mongodb)
    return templates.TemplateResponse(
        "transactions_search/transaction_count.html",
        {
            "request": request,
            "env": request.app.env,
            "user": user,
            "net": net,
            "all_projects": all_projects,
            "all_transaction_effects": all_transaction_effects,
        },
    )


@router.get("/{net}/transactions-search", response_class=HTMLResponse)
async def transactions_search(
    request: Request,
    net: str,
):
    user: UserV2 = get_user_detailsv2(request)
    return templates.TemplateResponse(
        "transactions_search/start.html",
        {"request": request, "env": request.app.env, "user": user, "net": net},
    )


@router.get(
    "/ajax_transactions_search/{net}/{transfer_type}/{gte}/{lte}/{start_date}/{end_date}/{current_page}/{sort_on}/{sort_direction}/{all}/{memo_only}/{scheduled}/{memo_contains}",
    response_class=HTMLResponse,
)
async def request_transactions_mongodb(
    request: Request,
    net: str,
    transfer_type: str,
    gte: str,
    lte: str,
    start_date: str,
    end_date: str,
    current_page: str,
    sort_on: str,
    sort_direction: int,
    all: str,
    memo_only: str,
    scheduled: str,
    memo_contains: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    mongomotor: MongoMotor = Depends(get_mongo_motor),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
    transfer_memos: dict = Depends(get_memo_transfers),
    contracts_with_tag_info_both_nets: dict = Depends(get_contracts_with_tag_info),
    ccd_historical: dict = Depends(get_exchange_rates_ccd_historical),
    # token_addresses_with_markup: dict = Depends(get_token_addresses_with_markup),
    credential_issuers: list = Depends(get_credential_issuers),
    blocks_per_day: dict[str, MongoTypeBlockPerDay] = Depends(get_blocks_per_day),
):
    """
    Endpoint to search for transactions given parameters.
    Parameter `all` refers to regular transfers.
    Attributes:

    Returns:

    """
    contracts_with_tag_info = contracts_with_tag_info_both_nets[NET(net)]
    user: UserV2 = get_user_detailsv2(request)
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet

    if memo_contains != "<empty string>":
        tooter.send(
            channel=TooterChannel.NOTIFIER,
            message=f'{user_string(user)} searched for "{memo_contains}".',
            notifier_type=TooterType.INFO,
        )

        filter_on_tx_hashes = True
        keys_with_sub_string = []
        memo_contains_lower = memo_contains.lower()
        for x in transfer_memos.keys():
            memo = x
            try:
                if memo_contains_lower in memo:
                    keys_with_sub_string.append(memo)
            except Exception as e:
                print(e)
                pass

        hashes_with_sub_string = [transfer_memos[x] for x in keys_with_sub_string]

        list_of_tx_hashes_with_memo_predicate = [
            item for sublist in hashes_with_sub_string for item in sublist
        ]
    else:
        list_of_tx_hashes_with_memo_predicate = []
        filter_on_tx_hashes = False

    # this is the case if we are paginating a page forward or backward
    if current_page.isnumeric():
        current_page = int(current_page)
        limit = 20
        skip = current_page * limit
    # this is the case if we do start or end
    else:
        # only for last do we have `:`, as we need to supply the remaining nr of txs to show.
        if ":" in current_page:
            [_, current_page] = current_page.split(":")[1].split("-")

            current_page = int(current_page)
            limit = 20
            skip = current_page * limit
        else:
            # we are requesting the first page
            current_page = 0
            limit = 20
            skip = current_page * limit

    try:
        gte = int(gte.replace(",", "").replace(".", ""))
        lte = int(lte.replace(",", "").replace(".", ""))

        if lte == 0:
            lte = 100_000
        start_date_dt = dateutil.parser.parse(start_date).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_date_dt = dateutil.parser.parse(end_date).replace(
            hour=23, minute=59, second=59, microsecond=999
        )
        amended_start_date = (
            f"{(dateutil.parser.parse(start_date)-dt.timedelta(days=1)):%Y-%m-%d}"
        )
        # start_block = recurring.blocks_at_end_of_day.get(
        #     amended_start_date, {"blockHeight": 0}
        # )["blockHeight"]
        # start_block = max(start_block - 6840, 0)
        # end_block = recurring.blocks_at_end_of_day.get(
        #     end_date, {"blockHeight": 1_000_000_000}
        # )["blockHeight"]
        # start_block = blocks_per_day.get(amended_start_date)

        start_block = blocks_per_day.get(amended_start_date)
        if start_block:
            start_block = start_block.height_for_first_block
        else:
            start_block = 0

        # start_block = max(start_block - 6840, 0)

        # end_block = recurring.blocks_at_end_of_day.get(
        #     end_date, {"blockHeight": 1_000_000_000}
        # )["blockHeight"]

        end_block = blocks_per_day.get(end_date)
        if end_block:
            end_block = end_block.height_for_last_block
        else:
            end_block = 1_000_000_000
    except:
        error = True

    all = False if all == "false" else True
    memo_only = False if memo_only == "false" else True
    scheduled = False if scheduled == "false" else True

    if all:
        transfer_type = "account_transfer"
        filter_on_tx_hashes = False
    elif scheduled:
        transfer_type = "transferred_with_schedule"
        filter_on_tx_hashes = False
    else:
        transfer_type = "account_transfer"

    if all:
        txs_hashes = []
    else:
        pipeline = mongodb.search_transfers_based_on_indices_v2(
            transfer_type,
            gte,
            lte,
            start_block,
            end_block,
            list_of_tx_hashes_with_memo_predicate,
            filter_on_tx_hashes,
        )
        result_txs_for_account = (
            await mongomotor.mainnet[Collections.involved_accounts_transfer]
            .aggregate(pipeline)
            .to_list(20)
        )
        txs_hashes = [x["_id"] for x in result_txs_for_account]

    # now apply hashes to collection transactions to filter

    pipeline = mongodb.search_transfers_mongo_v2(
        transfer_type,
        gte,
        lte,
        start_date_dt,
        end_date_dt,
        skip,
        limit,
        txs_hashes,
        sort_on,
        sort_direction,
        filter_on_tx_hashes,
    )
    result = list(db_to_use[Collections.transactions].aggregate(pipeline))

    txs = [CCD_BlockItemSummary(**x) for x in result[0]["data"]]
    if "total" in result[0]:
        len_search_result = result[0]["total"]
    else:
        len_search_result = 0

    tx_tabs: dict[TransactionClassifier, list] = {}
    tx_tabs_active: dict[TransactionClassifier, bool] = {}

    for tab in TransactionClassifier:
        tx_tabs[tab] = []

    for transaction in txs:
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
        None, len_search_result, current_page, tx_tabs, tx_tabs_active
    )

    for tab in TransactionClassifier:
        html += process_transactions_to_HTML(
            tx_tabs[tab], tab.value, tx_tabs_active[tab], tags
        )

    html += transactions_html_footer()
    return html
