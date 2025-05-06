from ccdexplorer_fundamentals.user_v2 import UserV2
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
import datetime as dt
from app.env import environment
from app.jinja2_helpers import templates
from app.state import (
    get_httpx_client,
    get_original_labeled_accounts,
    get_labeled_accounts,
    get_user_detailsv2,
)
from app.utils import get_url_from_api, verbose_timedelta
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
            "filename": f"nodes-and-validators (generated on {dt.datetime.now():%Y-%m-%d %H-%M-%S}).csv",
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
    len_validator_nodes = len(nodes_validators["validator_nodes_by_account_id"])
    len_reporting_validators = len(nodes_validators["validator_nodes_by_account_id"])
    len_non_validator_nodes = len(nodes_validators["non_validator_nodes_by_node_id"])
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
            "len_non_validator_nodes": len_non_validator_nodes,
            "len_validator_nodes": len_validator_nodes,
        },
    )


@router.get("/mainnet/ajax_nodes_tabulator", response_class=Response)
async def get_ajax_nodes_tabulator(
    request: Request,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/mainnet/accounts/nodes-validators",
        httpx_client,
    )
    nodes_validators = api_result.return_value if api_result.ok else {}
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/mainnet/accounts/last-payday-block/info",
        httpx_client,
    )
    last_payday_block = api_result.return_value if api_result.ok else None
    len_nodes = len(nodes_validators["all_nodes_by_node_id"])
    len_validators = len(nodes_validators["all_validators_by_validator_id"])
    len_reporting_validators = len(nodes_validators["validator_nodes_by_account_id"])

    all = {
        **nodes_validators["validator_nodes_by_account_id"],
        **nodes_validators["non_validator_nodes_by_node_id"],
        **nodes_validators["non_reporting_validators_by_validator_id"],
    }
    # dict(dict(
    # nodes_validators.validator_nodes_by_account_id, **
    # nodes_validators.non_validator_nodes_by_node_id), **
    # nodes_validators.non_reporting_validators_by_validator_id)
    flat_data = []
    for _id, node_info in all.items():
        node = node_info.get("node")
        validator = node_info.get("validator")

        flat_data.append(
            {
                "id": _id,
                "name": node.get("nodeName") if node else "Not reporting",
                "node": node.get("nodeId") if node else None,
                "baker_id": validator.get("baker_id") if validator else None,
                "stake": (
                    validator.get("pool_status", {})
                    .get("current_payday_info", {})
                    .get("lottery_power")
                    if validator
                    else None
                ),
                "ping": node.get("averagePing") if node else None,
                "version": node.get("client") if node else None,
                "peers": node.get("peersCount") if node else None,
                "uptime": (
                    (
                        dt.datetime.now().astimezone(dt.UTC)
                        - dt.timedelta(milliseconds=node.get("uptime"))
                    ).isoformat()
                    if node and isinstance(node.get("uptime"), int)
                    else None
                ),
            }
        )

    return JSONResponse(flat_data)
    # return templates.TemplateResponse(
    #     "/nodes/nodes_ajax.html",
    #     {
    #         "env": environment,
    #         "request": request,
    #         "user": user,
    #         "tags": tags,
    #         "net": net,
    #         "category": category,
    #         "last_payday_block": last_payday_block,
    #         "nodes_validators": nodes_validators,
    #         "len_nodes": len_nodes,
    #         "len_validators": len_validators,
    #         "len_reporting_validators": len_reporting_validators,
    #     },
    # )
