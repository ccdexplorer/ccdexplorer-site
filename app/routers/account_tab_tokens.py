import math
from typing import Optional

import httpx
import polars as polars
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_BlockItemSummary,
)
from ccdexplorer_fundamentals.user_v2 import UserV2
from fastapi import APIRouter, Depends, Query, Request
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
    create_dict_for_tabulator_display_for_fungible_token,
    create_dict_for_tabulator_display_for_non_fungible_token,
    create_dict_for_tabulator_display_for_unverified_token,
    create_dict_for_tabulator_display_for_plt_token,
    get_url_from_api,
)

router = APIRouter()


@router.get(
    "/account/tokens-tab-content/{net}/{account_id}", response_class=HTMLResponse
)
async def tokens_tab_content(
    request: Request,
    net: str,
    account_id: str,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 | None = await get_user_detailsv2(request)

    return templates.get_template("account/account_tokens.html").render(
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


@router.get(
    "/ajax_account_plt_tokens/{net}/{account_id}",
    response_class=HTMLResponse,
)
async def get_ajax_plt_tokens_(
    request: Request,
    net: str,
    account_id: str,
    page: int = Query(),
    size: int = Query(),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
    # recurring: Recurring = Depends(get_recurring),
    tags: dict = Depends(get_labeled_accounts),
):
    """
    Protocol-level tokens for an account.
    """
    skip = (page - 1) * size

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{account_id}/plt/{skip}/{size}",
        httpx_client,
    )
    api_return_result = api_result.return_value if api_result.ok else None
    if not api_return_result:
        error = (
            f"Request error getting PLT tokens for account at {account_id} on {net}."
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
        tb_made_up_rows = []
        result_rows = api_return_result["tokens"]

        if len(result_rows) > 0:
            for row in result_rows:
                tb_made_up_rows.append(
                    create_dict_for_tabulator_display_for_plt_token(net, row)
                )
        total_rows = api_return_result["total_token_count"]
        last_page = math.ceil(total_rows / size)
        return JSONResponse(
            {
                "data": tb_made_up_rows,
                "last_page": max(1, last_page),
                "last_row": total_rows,
            }
        )


@router.get(
    "/ajax_account_tokens/{net}/fungible-verified/{account_id}",
    response_class=HTMLResponse,
)
async def get_ajax_tokens_fungible_verified(
    request: Request,
    net: str,
    account_id: str,
    page: int = Query(),
    size: int = Query(),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
    # recurring: Recurring = Depends(get_recurring),
    tags: dict = Depends(get_labeled_accounts),
):
    """
    Fungible verified tokens for an account.
    """
    skip = (page - 1) * size
    # also used for smart contracts
    account_id = account_id.replace("&lt;", "<").replace("&gt;", ">")

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{account_id}/fungible-tokens/{skip}/{size}/verified",
        httpx_client,
    )
    api_return_result = api_result.return_value if api_result.ok else None
    if not api_return_result:
        error = f"Request error getting tokens for account at {account_id} on {net}."
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
        tb_made_up_rows = []
        result_rows = api_return_result["tokens"]

        if len(result_rows) > 0:
            for row in result_rows:
                tb_made_up_rows.append(
                    create_dict_for_tabulator_display_for_fungible_token(net, row)
                )
        total_rows = api_return_result["total_token_count"]
        last_page = math.ceil(total_rows / size)
        return JSONResponse(
            {
                "data": tb_made_up_rows,
                "last_page": max(1, last_page),
                "last_row": total_rows,
            }
        )


@router.get(
    "/ajax_account_tokens/{net}/non-fungible-verified/{account_id}",
    response_class=HTMLResponse,
)
async def get_ajax_tokens_non_fungible_verified(
    request: Request,
    net: str,
    account_id: str,
    page: int = Query(),
    size: int = Query(),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
    # recurring: Recurring = Depends(get_recurring),
    tags: dict = Depends(get_labeled_accounts),
):
    """
    Fungible verified tokens for an account.
    """
    skip = (page - 1) * size
    # also used for smart contracts
    account_id = account_id.replace("&lt;", "<").replace("&gt;", ">")
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{account_id}/non-fungible-tokens/{skip}/{size}/verified",
        httpx_client,
    )
    api_return_result = api_result.return_value if api_result.ok else None
    if not api_return_result:
        error = f"Request error getting tokens for account at {account_id} on {net}."
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
        tb_made_up_rows = []
        result_rows = api_return_result["tokens"]

        if len(result_rows) > 0:
            for row in result_rows:
                tb_made_up_rows.append(
                    create_dict_for_tabulator_display_for_non_fungible_token(net, row)
                )
        total_rows = api_return_result["total_token_count"]
        last_page = math.ceil(total_rows / size)
        return JSONResponse(
            {
                "data": tb_made_up_rows,
                "last_page": max(1, last_page),
                "last_row": total_rows,
            }
        )


@router.get(
    "/ajax_account_tokens/{net}/unverified/{account_id}",
    response_class=HTMLResponse,
)
async def get_ajax_tokens_unverified(
    request: Request,
    net: str,
    account_id: str,
    page: int = Query(),
    size: int = Query(),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
    # recurring: Recurring = Depends(get_recurring),
    tags: dict = Depends(get_labeled_accounts),
):
    """
    Fungible verified tokens for an account.
    """
    skip = (page - 1) * size
    # also used for smart contracts
    account_id = account_id.replace("&lt;", "<").replace("&gt;", ">")

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{account_id}/tokens/{skip}/{size}/unverified",
        httpx_client,
    )
    api_return_result = api_result.return_value if api_result.ok else None
    if not api_return_result:
        error = f"Request error getting tokens for account at {account_id} on {net}."
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
        tb_made_up_rows = []
        result_rows = api_return_result["tokens"]

        if len(result_rows) > 0:
            for row in result_rows:
                tb_made_up_rows.append(
                    create_dict_for_tabulator_display_for_unverified_token(net, row)
                )
        total_rows = api_return_result["total_token_count"]
        last_page = math.ceil(total_rows / size)
        return JSONResponse(
            {
                "data": tb_made_up_rows,
                "last_page": max(1, last_page),
                "last_row": total_rows,
            }
        )
