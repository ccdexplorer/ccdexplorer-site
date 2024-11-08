from ccdexplorer_fundamentals.user_v2 import UserV2
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.env import environment
from app.jinja2_helpers import templates
from app.state import (
    get_httpx_client,
    get_original_labeled_accounts,
    get_labeled_accounts,
    get_user_detailsv2,
)
from app.utils import get_url_from_api
import httpx

router = APIRouter()


@router.get("/{net}/nodes", response_class=HTMLResponse | RedirectResponse)
async def nodes(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 = await get_user_detailsv2(request)
    request.state.api_calls = {}
    request.state.api_calls["Nodes and Validators"] = (
        f"{request.app.api_url}/docs#/Accounts/get_nodes_and_validators_v2__net__accounts_nodes_validators_get"
    )
    request.state.api_calls["Last Payday Info"] = (
        f"{request.app.api_url}/docs#/Accounts/get_last_payday_info_v2__net__accounts_last_payday_block_info_get"
    )
    return templates.TemplateResponse(
        "/nodes/nodes.html",
        {
            "env": environment,
            "request": request,
            "user": user,
            "tags": tags,
            "net": net,
        },
    )


@router.get(
    "/ajax_nodes_to_html/{net}/{category}/{key}/{direction}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_nodes_v2(
    request: Request,
    net: str,
    category: str,
    key: str,
    direction: str,
    api_key: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/accounts/nodes-validators",
        httpx_client,
    )
    nodes_validators = api_result.return_value if api_result.ok else {}
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/accounts/last-payday-block/info",
        httpx_client,
    )
    last_payday_block = api_result.return_value if api_result.ok else None
    len_nodes = len(nodes_validators["all_nodes_by_node_id"])
    len_validators = len(nodes_validators["all_validators_by_validator_id"])
    len_reporting_validators = len(nodes_validators["validator_nodes_by_account_id"])

    return templates.TemplateResponse(
        "/nodes/nodes_ajax.html",
        {
            "env": environment,
            "request": request,
            "user": user,
            "tags": tags,
            "net": net,
            "category": category,
            "last_payday_block": last_payday_block,
            "nodes_validators": nodes_validators,
            "len_nodes": len_nodes,
            "len_validators": len_validators,
            "len_reporting_validators": len_reporting_validators,
        },
    )
