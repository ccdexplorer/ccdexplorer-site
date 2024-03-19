# ruff: noqa: F403, F405, E402, E501, E722

import datetime as dt
from datetime import timedelta
import logging
import uuid
import resource
import uvicorn
import urllib3
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi_restful.tasks import repeat_every
from contextlib import asynccontextmanager
from ccdefundamentals.mongodb import MongoDB, MongoMotor
from prometheus_fastapi_instrumentator import Instrumentator

# from app.Recurring import account


from app.jinja2_helpers import *

# from app.__chain import *
from app.state.state import *

urllib3.disable_warnings()

from ccdefundamentals.ccdscan import CCDScan
from ccdefundamentals.GRPCClient import GRPCClient
from app.ajax_helpers import *
from app.classes.dressingroom import *
from app.classes.Node_Baker import *


from app.console import console
from env import *
from app.Recurring.recurring import Recurring
from app.routers import (
    admin,
    account,
    block,
    exchanges,
    misc,
    nodes_bakers,
    smart_contracts,
    staking,
    statistics,
    tokens,
    transaction,
    transactions,
    usecases,
    usersv2,
)

from ccdefundamentals.tooter import Tooter, TooterType, TooterChannel

grpcclient = GRPCClient()
tooter = Tooter()

mongodb = MongoDB(tooter)
motormongo = MongoMotor(tooter)

ccdscan = CCDScan(tooter)


async def find_release():
    pp = [{"$sort": {"date": -1}}, {"$limit": 1}]
    release = list(mongodb.utilities[CollectionsUtilities.release_notes].aggregate(pp))[
        0
    ]

    return release["_id"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    instrumentator.expose(app, endpoint="/api/v1/metrics")
    s = dt.datetime.now().astimezone(dt.timezone.utc)
    app.env = environment
    app.grpcclient = grpcclient
    app.tooter = tooter
    app.ccdscan = ccdscan
    app.recurring = recurring
    console.log(
        f"startup_initial before mongo: {(dt.datetime.now().astimezone(dt.timezone.utc)-s).total_seconds():,.4} s"
    )
    s = dt.datetime.now().astimezone(dt.timezone.utc)
    app.mongodb = mongodb
    app.motormongo = motormongo
    app.env["API_KEY"] = str(uuid.uuid1())
    console.log(
        f"startup_initial mongo / server: {(dt.datetime.now().astimezone(dt.timezone.utc)-s).total_seconds():,.4} s"
    )
    s = dt.datetime.now().astimezone(dt.timezone.utc)
    app.release = await find_release()
    app.user_last_requested = dt.datetime.now().astimezone(dt.timezone.utc) - timedelta(
        seconds=10
    )
    app.tokens_tags_last_requested = dt.datetime.now().astimezone(
        dt.timezone.utc
    ) - timedelta(seconds=10)
    app.labeled_accounts_last_requested = dt.datetime.now().astimezone(
        dt.timezone.utc
    ) - timedelta(seconds=10)
    app.exchange_rates_last_requested = dt.datetime.now().astimezone(
        dt.timezone.utc
    ) - timedelta(seconds=10)
    app.memo_transfers_last_requested = dt.datetime.now().astimezone(
        dt.timezone.utc
    ) - timedelta(seconds=10)
    app.blocks_per_day_last_requested = dt.datetime.now().astimezone(
        dt.timezone.utc
    ) - timedelta(seconds=10)
    app.paydays_per_day_last_requested = dt.datetime.now().astimezone(
        dt.timezone.utc
    ) - timedelta(seconds=10)
    app.exchange_rates_ccd_historical_last_requested = dt.datetime.now().astimezone(
        dt.timezone.utc
    ) - timedelta(seconds=10)
    app.nightly_accounts_last_requested = dt.datetime.now().astimezone(
        dt.timezone.utc
    ) - timedelta(seconds=10)
    app.exchange_rates_historical_last_requested = dt.datetime.now().astimezone(
        dt.timezone.utc
    ) - timedelta(seconds=10)
    app.credential_issuers_last_requested = dt.datetime.now().astimezone(
        dt.timezone.utc
    ) - timedelta(seconds=10)
    app.reporting_output_last_requested = dt.datetime.now().astimezone(
        dt.timezone.utc
    ) - timedelta(seconds=10)
    app.contracts_with_tag_info = None
    app.tags = None
    app.memo_transfers = None
    app.user = None
    app.exchange_rates = None
    app.exchange_rates_ccd_historical = None
    app.exchange_rates_historical = None
    app.credential_issuers = None
    app.blocks_per_day = None
    app.paydays_per_day = None
    app.paydays_last_blocks_validated = None
    app.nightly_accounts_by_account_id = None
    app.reporting_output = {}
    app.net = NET.MAINNET
    app.env = environment
    app.cns_response = {"updated": False}
    app.last_block_response = {
        NET.MAINNET: None,
        NET.TESTNET: None,
    }
    app.last_seen_finalized_height = {
        NET.MAINNET: 0,
        NET.TESTNET: 0,
    }

    s = dt.datetime.now().astimezone(dt.timezone.utc)
    recurring.refresh_nodes_from_collection()
    console.log(
        f"refresh_nodes_from_collection: {(dt.datetime.now().astimezone(dt.timezone.utc)-s).total_seconds():,.4} s"
    )

    s = dt.datetime.now().astimezone(dt.timezone.utc)
    await get_nightly_accounts(app)
    console.log(
        f"refresh_nightly: {(dt.datetime.now().astimezone(dt.timezone.utc)-s).total_seconds():,.4} s"
    )

    app.grpcclient.check_connection()
    yield
    print("END")
    pass


app = FastAPI(lifespan=lifespan)

# should be above the routers
instrumentator = Instrumentator().instrument(app)

app.include_router(smart_contracts.router)
app.include_router(block.router)
app.include_router(admin.router)
app.include_router(usecases.router)
app.include_router(misc.router)
app.include_router(account.router)
app.include_router(staking.router)
app.include_router(tokens.router)
app.include_router(transaction.router)
app.include_router(statistics.router)
app.include_router(nodes_bakers.router)
app.include_router(exchanges.router)
app.include_router(transactions.router)
app.include_router(usersv2.router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

origins = [
    "http://127.0.0.1:8000",
    "https://127.0.0.1:8000",
    "http://dev.concordium-explorer.nl",
    "https://dev.concordium-explorer.nl",
    "http://concordium-explorer.nl",
    "https://concordium-explorer.nl",
    "http://ccdexplorer.io",
    "https://ccdexplorer.io",
    "http://dev.ccdexplorer.io",
    "https://dev.ccdexplorer.io",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


console.log(
    f"Memory usage before mongo: {(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024):,.0f} Mb"
)
recurring = Recurring(ccdscan, mongodb, motormongo, grpcclient)


tooter.send(
    channel=TooterChannel.NOTIFIER,
    message="(Site): Starting up.",
    notifier_type=TooterType.INFO,
)


@repeat_every(seconds=60, wait_first=False)
async def refresh_nodes_from_collection():
    s = dt.datetime.now()
    recurring.refresh_nodes_from_collection()
    console.log(
        f"refresh_nodes_from_collection: {(dt.datetime.now()-s).total_seconds():,.4} s"
    )


@repeat_every(seconds=60 * 11, wait_first=False)
async def refresh_nightly():
    s = dt.datetime.now()
    await get_nightly_accounts(app)
    console.log(f"refresh_nightly: {(dt.datetime.now()-s).total_seconds():,.4} s")


@repeat_every(seconds=5, wait_first=False)
async def check_connection():
    app.grpcclient.check_connection()
