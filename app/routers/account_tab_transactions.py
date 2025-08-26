import math
from typing import Optional

import httpx
import polars as polars
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_BlockItemSummary,
)
from ccdexplorer_fundamentals.user_v2 import UserV2
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.classes.dressingroom import (
    MakeUp,
    MakeUpRequest,
    RequestingRoute,
)
from app.env import environment
from app.jinja2_helpers import templates
from app.state import get_httpx_client, get_labeled_accounts, get_user_detailsv2
from app.utils import (
    create_dict_for_tabulator_display,
    get_url_from_api,
)

router = APIRouter()


@router.get(
    "/account/transactions-tab-content/{net}/{account_id}", response_class=HTMLResponse
)
async def transactions_tab_content(
    request: Request,
    net: str,
    account_id: str,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 | None = await get_user_detailsv2(request)

    return templates.get_template("account/account_transactions.html").render(
        {
            "net": net,
            "account_id": account_id,
            "user": user,
            "env": request.app.env,
        }
    )


class SortItem(BaseModel):
    field: str
    dir: str


class FilterItem(BaseModel):
    field: str
    type: str
    value: str


class TabulatorRequest(BaseModel):
    page: int
    size: int
    sort: Optional[list[SortItem]] = []
    filter: Optional[list[FilterItem]] = []


@router.post(
    "/account_transactions_with_filter/{net}/{account_id}",
    response_class=HTMLResponse,
)
async def get_account_transactions_with_filter_for_tabulator(
    request: Request,
    net: str,
    account_id: str,
    body: TabulatorRequest,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
    # recurring: Recurring = Depends(get_recurring),
    tags: dict = Depends(get_labeled_accounts),
):
    """
    Transactions for account.
    """

    user: UserV2 | None = await get_user_detailsv2(request)

    skip = (body.page - 1) * body.size

    if body.sort and len(body.sort) > 0:
        sort_key = body.sort[0].field
        direction = body.sort[0].dir
    else:
        sort_key = "block_height"
        direction = "desc"

    if body.filter and len(body.filter) > 0:
        filter_value = body.filter[0].value

    else:
        filter_value = "all"

    # sort_key = "effect_type" if sort_key == "transaction.type.contents" else sort_key
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{account_id}/transactions/{skip}/{body.size}/{sort_key}/{direction}/{filter_value}",
        httpx_client,
    )
    tx_result = api_result.return_value if api_result.ok else None
    if not tx_result:
        error = (
            f"Request error getting transactions for account at {account_id} on {net}."
        )
        return templates.TemplateResponse(
            "base/error-request.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )
    else:
        tb_made_up_txs = []
        tx_result_transactions = tx_result["transactions"]

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

                type_additional_info, sender = (
                    await classified_tx.transform_for_tabulator()
                )

                tb_made_up_txs.append(
                    create_dict_for_tabulator_display(
                        net, classified_tx, type_additional_info, sender
                    )
                )
        total_rows = tx_result["total_tx_count"]
        last_page = math.ceil(total_rows / body.size)
        return JSONResponse(
            {
                "data": tb_made_up_txs,
                "last_page": max(1, last_page),
                "last_row": total_rows,
            }
        )
