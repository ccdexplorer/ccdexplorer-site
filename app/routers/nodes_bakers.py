# ruff: noqa: F403, F405, E402
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from app.Recurring.recurring import Recurring
from app.jinja2_helpers import *
from app.env import *
from app.state.state import *
from pymongo import DESCENDING
from app.ajax_helpers import process_nodes_to_HTML
from ccdexplorer_fundamentals.user_v2 import UserV2, NotificationPreferences
from ccdexplorer_fundamentals.node import ConcordiumNodeFromDashboard

from ccdexplorer_fundamentals.tooter import Tooter, TooterType, TooterChannel
from ccdexplorer_fundamentals.mongodb import MongoDB, Collections, MongoTypePayday
import aiohttp
from ccdexplorer_fundamentals.GRPCClient import GRPCClient


router = APIRouter()


@router.get("/ajax_get_node/{net}/{node_id}", response_class=HTMLResponse)
async def get_ajax_node(
    request: Request,
    net: str,
    node_id: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    recurring: Recurring = Depends(get_recurring),
    tags: dict = Depends(get_labeled_accounts),
):
    """
    Endpoint to display an individual node.
    Attributes:
        node_id (str): the id from the node (as reported by the dashboard).
    Returns:
        template (HTMLResponse): node/node.html
    """
    user: UserV2 = get_user_detailsv2(request)
    node = None
    async with aiohttp.ClientSession() as session:
        if net == "testnet":
            url = "https://dashboard.testnet.concordium.com/nodesSummary"
        else:
            url = "https://dashboard.mainnet.concordium.software/nodesSummary"
        async with session.get(url) as resp:
            t = await resp.json()
            nodes = {}
            for raw_node in t:
                raw_node = ConcordiumNodeFromDashboard(**raw_node)
                nodes[raw_node.nodeId] = raw_node
                if raw_node.nodeId == node_id:
                    node = raw_node
    if not node:
        error = "Incorrect node id..."
    else:
        error = None
    return templates.TemplateResponse(
        "node/node_info.html",
        {
            "request": request,
            "env": request.app.env,
            "node": node,
            "node_id": node_id,
            "error": error,
            "user": user,
            "net": net,
            "nodes": nodes,
        },
    )


@router.get("/{net}/node/{node_id}", response_class=HTMLResponse)
async def get_node(
    request: Request,
    net: str,
    node_id: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    recurring: Recurring = Depends(get_recurring),
    tags: dict = Depends(get_labeled_accounts),
):
    """
    Endpoint to display an individual node.
    Attributes:
        node_id (str): the id from the node (as reported by the dashboard).
    Returns:
        template (HTMLResponse): node/node.html
    """
    user: UserV2 = get_user_detailsv2(request)

    return templates.TemplateResponse(
        "node/node.html",
        {
            "request": request,
            "env": request.app.env,
            "node_id": node_id,
            "user": user,
            "net": net,
            "nodes": recurring.all_nodes_by_node_id,
        },
    )


@router.get(
    "/ajax_nodes_html_v2/{net}/{key}/{direction}/{api_key}", response_class=HTMLResponse
)
async def get_ajax_nodes_v2(
    request: Request,
    net: str,
    key: str,
    direction: str,
    api_key: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    tooter: Tooter = Depends(get_tooter),
    tags: dict = Depends(get_labeled_accounts),
):
    user: UserV2 = get_user_detailsv2(request)
    if net == "mainnet":
        if api_key != request.app.env["API_KEY"]:
            return "No valid api key supplied."
        else:
            last_payday = MongoTypePayday(
                **mongodb.mainnet[Collections.paydays].find_one(sort=[("date", -1)])
            )
            recurring.list_to_sort = (
                list(recurring.baker_nodes_by_baker_id.values())
                + list(recurring.non_reporting_bakers_by_baker_id.values())
                + list(recurring.non_baker_nodes_by_node_id.values())
            )
            recurring.sort_nodes_from_class(key, direction)
            show_bakers = True
            html = process_nodes_to_HTML(
                recurring.sorted_nodes,
                last_payday,
                key,
                direction,
                len(recurring.all_nodes),
                len(recurring.all_bakers_by_baker_id),
                len(recurring.all_bakers_by_baker_id)
                - len(recurring.non_reporting_bakers_by_baker_id),
                recurring.baker_nodes_by_baker_id,
                recurring.non_reporting_bakers_by_baker_id,
                recurring.non_baker_nodes_by_node_id,
                show_bakers,
                user,
                tags,
                net,
            )
            return html
    else:
        return templates.TemplateResponse(
            "testnet/not-available-single.html",
            {
                "env": request.app.env,
                "request": request,
                "net": net,
                "user": user,
            },
        )


@router.get("/bakers", response_class=RedirectResponse)
async def bakers(request: Request):
    return "/nodes-and-validators"


@router.get("/nodes", response_class=RedirectResponse)
async def bakers(request: Request):
    return "/nodes-and-validators"


@router.get("/nodes-and-bakers", response_class=RedirectResponse)
async def nodes_bakers(request: Request):
    return "/nodes-and-validators"


@router.get("/{net}/nodes-and-validators", response_class=HTMLResponse)
async def nodes(
    request: Request,
    net: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    tooter: Tooter = Depends(get_tooter),
):
    user: UserV2 = get_user_detailsv2(request)

    return templates.TemplateResponse(
        "nodes_with_ajax.html",
        {
            "env": request.app.env,
            "request": request,
            "net": net,
            "user": user,
        },
    )
