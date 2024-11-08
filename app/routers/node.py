import datetime as dt

import dateutil
import httpx
import plotly.express as px
import polars as polars
from ccdexplorer_fundamentals.credential import Identity
from ccdexplorer_fundamentals.cis import MongoTypeTokensTag
from ccdexplorer_fundamentals.node import ConcordiumNodeFromDashboard
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_AccountInfo,
    CCD_BlockItemSummary,
    CCD_PoolInfo,
)
from app.classes.sankey import SanKey
from ccdexplorer_fundamentals.user_v2 import UserV2
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from app.classes.dressingroom import (
    MakeUp,
    MakeUpRequest,
    RequestingRoute,
)
import json
from app.env import environment

# from .account_validator import get_pool_info, get_earliest_win_time
from app.jinja2_helpers import templates
from app.state import get_httpx_client, get_labeled_accounts, get_user_detailsv2
from app.utils import (
    PaginationRequest,
    account_link,
    calculate_skip,
    pagination_calculator,
    ccdexplorer_plotly_template,
    verbose_timedelta,
    get_url_from_api,
)
import plotly.graph_objects as go
from plotly.subplots import make_subplots

router = APIRouter()


@router.get("/{net}/node/{node_id}", response_class=HTMLResponse)
async def get_node(
    request: Request,
    net: str,
    node_id: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    """
    Endpoint to display an individual node.
    Attributes:
        node_id (str): the id from the node (as reported by the dashboard).
    Returns:
        template (HTMLResponse): node/node.html
    """
    user: UserV2 = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/misc/node/{node_id}", httpx_client
    )
    node = api_result.return_value if api_result.ok else None

    return templates.TemplateResponse(
        "node/node.html",
        {
            "request": request,
            "node": node,
            "env": request.app.env,
            "node_id": node_id,
            "user": user,
            "net": net,
            # "nodes": recurring.all_nodes_by_node_id,
        },
    )


@router.get("/ajax_get_node/{net}/{node_id}", response_class=HTMLResponse)
async def get_ajax_node(
    request: Request,
    net: str,
    node_id: str,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    """
    Endpoint to display an individual node.
    Attributes:
        node_id (str): the id from the node (as reported by the dashboard).
    Returns:
        template (HTMLResponse): node/node.html
    """
    user: UserV2 = await get_user_detailsv2(request)
    node = None

    if net == "testnet":
        url = "https://dashboard.testnet.concordium.com/nodesSummary"
    else:
        url = "https://dashboard.mainnet.concordium.software/nodesSummary"

    api_result = await get_url_from_api(
        url,
        httpx_client,
    )
    r = api_result.return_value if api_result.ok else None

    nodes = {}
    for raw_node in r:
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
