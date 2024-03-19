# ruff: noqa: F403, F405, E402, E501, E722, F401
from fastapi import APIRouter, Request, Depends
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
    JSONResponse,
    StreamingResponse,
)
from app.classes.dressingroom import TransactionClassifier
from app.classes.Node_Baker import BakerStatus
from app.jinja2_helpers import *
from env import *
from app.state.state import *
import requests
from bson.json_util import dumps
from app.Recurring.recurring import Recurring
from ccdefundamentals.mongodb import MongoDB
from ccdefundamentals.GRPCClient import GRPCClient
from ccdefundamentals.user_v2 import (
    UserV2,
    NotificationPreferences,
)
from env import ADMIN_CHAT_ID
from typing import Iterable, cast
import docker
import json

router = APIRouter()


async def change_streamer(db_to_use):
    change_stream = db_to_use[Collections.helpers].watch()
    for change in change_stream:
        yield (dumps(change))


@router.get("/ajax_admin_stream", response_class=StreamingResponse)
async def admin_stream(
    request: Request,
    recurring: Recurring = Depends(get_recurring),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    mongodb: MongoDB = Depends(get_mongo_db),
    tags: dict = Depends(get_labeled_accounts),
):
    user: UserV2 = get_user_detailsv2(request)

    net = "mainnet"
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    # helpers_mainnet = db_to_use[Collections.helpers].find({})
    print("stream")
    return StreamingResponse(change_streamer(db_to_use))


@router.get("/admin", response_class=HTMLResponse)
async def admin_home(
    request: Request,
    # net: str,
    recurring: Recurring = Depends(get_recurring),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    mongodb: MongoDB = Depends(get_mongo_db),
    tags: dict = Depends(get_labeled_accounts),
):
    user: UserV2 = get_user_detailsv2(request)
    if user:
        if isinstance(user, dict):
            user = UserV2(**user)
        if not isinstance(user, UserV2):
            user = UserV2(**user)
    processed_users = []
    user_categories = {}
    net = "mainnet"
    db_to_use = mongodb.testnet if net == "testnet" else mongodb.mainnet
    helpers_mainnet = db_to_use[Collections.helpers].find({})

    # return StreamingResponse(change_streamer(mongodb))
    net = "testnet"
    helpers_testnet = db_to_use[Collections.helpers].find({})

    v2_users = [
        x
        for x in (
            mongodb.utilities[CollectionsUtilities.users_v2_prod]
            .find({})
            .sort("last_modified", -1)
        )
    ]

    if user:
        if user.telegram_chat_id == ADMIN_CHAT_ID:
            return templates.TemplateResponse(
                "admin/admin_home.html",
                {
                    "env": request.app.env,
                    "net": "mainnet",
                    "request": request,
                    "helpers_mainnet": helpers_mainnet,
                    "helpers_testnet": helpers_testnet,
                    "user": user,
                    "users": v2_users,
                    # "processed_users": processed_users,
                    # "count_messages": count_messages,
                    # "count_by_type": count_by_type,
                    # "subscription_details": SubscriptionDetails,
                    # "tags": tags,
                    # "total_paid_all_users": total_paid_all_users,
                    # "user_categories": user_categories,
                },
            )
        else:
            return templates.TemplateResponse(
                "admin/admin_no_access.html",
                {"env": request.app.env, "request": request},
            )
    else:
        return templates.TemplateResponse(
            "admin/admin_no_access.html", {"env": request.app.env, "request": request}
        )


@router.get("/ajax_admin_docker/{container_name}/{tail}", response_class=HTMLResponse)
async def ajax_admin_docker(request: Request, container_name: str, tail: int):
    user: UserV2 = get_user_detailsv2(request)
    if SITE_URL == "http://127.0.0.1:8000":
        docker_container_logs = b"""
            
[11:01:09] Blocks retrieved: 7,496,447 - 7,496,451                  main.py:1541\n
           Spent 0 sec on 4 txs.                                    main.py:1375\n
           Blocks processed: 7,496,447 - 7,496,451                  main.py:1401
           Sent to Mongo   : 7,496,447 - 7,496,451                  main.py:1198
           B:      5 | M     0 | Mod     0 | U     5                main.py:1201
           T:      4 | M     0 | Mod     0 | U     4                main.py:1213
[11:01:10] A:      4 | M     0 | Mod     0 | U     4                main.py:1222
           Block retrieved: 7,496,452                               main.py:1537
[11:01:11] Spent 0 sec on 0 txs.                                    main.py:1375
           Block processed: 7,496,452                               main.py:1399
           Sent to Mongo  : 7,496,452                               main.py:1194
           B:      1 | M     0 | Mod     0 | U     1                main.py:1201
[11:01:12] Block retrieved: 7,496,453                               main.py:1537
"""

    else:
        client = docker.from_env()
        docker_container = client.containers.list(filters={"name": container_name})
        docker_container_logs = (
            docker_container[0].logs(tail=tail) if len(docker_container) > 0 else None
        )

    logs = []
    for line in docker_container_logs.decode("utf-8") if docker_container_logs else []:
        logs.append(line)
    return templates.TemplateResponse(
        "admin/admin_docker_logs.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "docker_container_logs": logs,
        },
    )
    return


@router.get("/ajax_admin_mongo", response_class=HTMLResponse)
async def ajax_admin_mongo(
    request: Request,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request)
    output = mongodb.connection.admin.command("replSetGetStatus")
    mainnet_stats = mongodb.mainnet_db.command("dbStats")
    testnet_stats = mongodb.testnet_db.command("dbStats")
    return templates.TemplateResponse(
        "admin/admin_mongo.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "output": output,
            "mainnet_stats": mainnet_stats,
            "testnet_stats": testnet_stats,
        },
    )


@router.get("/ajax_admin_mongo_message_log", response_class=HTMLResponse)
async def ajax_admin_mongo_message_log(
    request: Request,
    mongodb: MongoDB = Depends(get_mongo_db),
):
    user: UserV2 = get_user_detailsv2(request)
    if user:
        if not isinstance(user, UserV2):
            user = UserV2(**user)
    message_logs = mongodb.utilities[CollectionsUtilities.message_log].aggregate(
        [{"$sort": {"block_height": -1}}, {"$limit": 25}]
    )

    # testnet_stats = mongodb.testnet_db.command("dbStats")
    return templates.TemplateResponse(
        "admin/admin_mongo_message_log.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "net": "mainnet",
            "message_logs": list(message_logs),
        },
    )


@router.get("/admin/docker", response_class=HTMLResponse)
async def admin_home(
    request: Request,
    # net: str,
    recurring: Recurring = Depends(get_recurring),
    grpcclient: GRPCClient = Depends(get_grpcclient),
    mongodb: MongoDB = Depends(get_mongo_db),
    tags: dict = Depends(get_labeled_accounts),
):
    user: UserV2 = get_user_detailsv2(request)
    if isinstance(user, dict):
        user = UserV2(**user)
    if not isinstance(user, UserV2):
        user = UserV2(**user)
    if user:
        if user.username == "sderuiter":
            return templates.TemplateResponse(
                "admin/admin_docker.html",
                {
                    "env": request.app.env,
                    "request": request,
                    "user": user,
                },
            )
        else:
            return templates.TemplateResponse(
                "admin/admin_no_access.html",
                {"env": request.app.env, "request": request},
            )
    else:
        return templates.TemplateResponse(
            "admin/admin_no_access.html", {"env": request.app.env, "request": request}
        )
