# ruff: noqa: F403, F405, E402, E501, E722, F401

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from app.classes.dressingroom import (
    MakeUp,
    TransactionClassifier,
    MakeUpRequest,
    RequestingRoute,
)
from ccdexplorer_fundamentals.transaction import Transaction

# from ccdexplorer_fundamentals.ccdscan import CCDScan
from ccdexplorer_fundamentals.tooter import Tooter, TooterType, TooterChannel

# import requests
# import json
from ccdexplorer_fundamentals.enums import NET
from ccdexplorer_fundamentals.mongodb import (
    MongoDB,
    Collections,
    MongoTypePayday,
    MongoTypePaydayAPYIntermediate,
    MongoTypeModule,
)
from ccdexplorer_fundamentals.GRPCClient import GRPCClient

from ccdexplorer_fundamentals.GRPCClient.CCD_Types import *
from app.jinja2_helpers import *
from app.env import *
from app.state.state import *

router = APIRouter()


@router.get("/project/{project_id}", response_class=HTMLResponse)
async def get_project_route(
    request: Request,
    project_id: str,
    mongodb: MongoDB = Depends(get_mongo_db),
    grpcclient: GRPCClient = Depends(get_grpcclient),
):

    project = mongodb.utilities[CollectionsUtilities.projects].find_one(
        {"project_id": project_id}
    )
    mainnet_project_addresses = list(
        mongodb.mainnet[Collections.projects].find({"project_id": project_id})
    )
    mainnet_accounts = [
        x for x in mainnet_project_addresses if x["type"] == "account_address"
    ]
    mainnet_contracts = [
        x for x in mainnet_project_addresses if x["type"] == "contract_address"
    ]
    if project:
        return templates.TemplateResponse(
            "projects/project_overview.html",
            {
                "request": request,
                "env": request.app.env,
                "project": project,
                "project_id": project_id,
                "display_name": project["display_name"],
                "mainnet_accounts": mainnet_accounts,
                "mainnet_contracts": mainnet_contracts,
                "net": "mainnet",
            },
        )


@router.get("/projects", response_class=HTMLResponse)
async def get_projects_route(
    request: Request,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    projects = get_all_project_ids(mongodb)
    return templates.TemplateResponse(
        "projects/projects.html",
        {
            "request": request,
            "env": request.app.env,
            "projects": projects,
            "net": "mainnet",
        },
    )
