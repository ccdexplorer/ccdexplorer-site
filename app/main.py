import uuid
from contextlib import asynccontextmanager
from ccdexplorer_fundamentals.tooter import Tooter
from app.env import environment
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import CCD_AccountInfo

# from fastapi_restful.tasks import repeat_every
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# import asyncio
# from scheduler.asyncio import Scheduler

from app.routers import home
from app.routers import transaction
from app.routers import block
from app.routers import account
from app.routers import account_validator
from app.routers import account_pool
from app.routers import node
from app.routers import smart_contracts
from app.routers import tools
from app.routers import projects
from app.routers import usersv2
from app.routers import statistics
from app.routers import tokens
from app.routers import nodes
from app.routers import staking
from app.utils import get_url_from_api, add_account_info_to_cache
import sentry_sdk
import datetime as dt
import httpx
import pickle

if environment["SITE_URL"] != "http://127.0.0.1:8000":
    sentry_sdk.init(
        dsn="https://f4713c02eb5646ed84b2642b0fa1501e@o4503924901347328.ingest.us.sentry.io/4503924903313408",
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for tracing.
        traces_sample_rate=1.0,
        _experiments={
            # Set continuous_profiling_auto_start to True
            # to automatically start the profiler on when
            # possible.
            "continuous_profiling_auto_start": True,
        },
    )

tooter = Tooter()
scheduler = AsyncIOScheduler(timezone=dt.UTC)


async def log_request(request):
    print(
        f"Request event hook: {request.method} {request.url} {request.headers} - Waiting for response"
    )


async def log_response(response):
    request = response.request
    print(
        f"Response event hook: {request.method} {request.url} {response.headers}- Status {response.status_code}"
    )


def read_addresses_if_available(app):
    app.addresses_to_indexes = {"mainnet": {}, "testnet": {}}
    try:
        for net in ["mainnet", "testnet"]:
            with open(
                f"addresses/{net}_addresses_to_indexes.pickle", "rb"
            ) as fp:  # Unpickling
                app.addresses_to_indexes[net] = pickle.load(fp)
    except Exception as _:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.templates = Jinja2Templates(directory="app/templates")
    app.api_url = environment["API_URL"]
    app.httpx_client = httpx.AsyncClient(
        # event_hooks={"request": [log_request], "response": [log_response]},
        timeout=None,
        headers={"x-ccdexplorer-key": environment["CCDEXPLORER_API_KEY"]},
    )
    app.env = environment
    app.tooter = tooter
    app.credential_issuers = None
    app.env["API_KEY"] = str(uuid.uuid1())
    now = dt.datetime.now().astimezone(dt.timezone.utc)
    app.labeled_accounts_last_requested = now - dt.timedelta(seconds=10)
    app.users_last_requested = now - dt.timedelta(seconds=10)
    app.nodes_last_requested = now - dt.timedelta(seconds=10)
    app.credential_issuers_last_requested = now - dt.timedelta(seconds=10)
    app.tags = None
    app.nodes = None
    read_addresses_if_available(app)
    app.schema_cache = {"mainnet": {}, "testnet": {}}
    app.token_information_cache = {"mainnet": {}, "testnet": {}}
    app.schema_cache = {"mainnet": {}, "testnet": {}}
    app.cns_domain_cache = {"mainnet": {}, "testnet": {}}
    app.blocks_cache = {"mainnet": [], "testnet": []}
    app.transactions_cache = {"mainnet": [], "testnet": []}
    app.accounts_cache = {"mainnet": [], "testnet": []}
    app.identity_providers_cache = {"mainnet": {}, "testnet": {}}
    await repeated_task_get_accounts_id_providers(app)
    scheduler.start()
    yield
    scheduler.shutdown()
    await app.httpx_client.aclose()
    print("END")
    pass


app = FastAPI(lifespan=lifespan)


app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/node", StaticFiles(directory="node_modules"), name="node_modules")
app.mount("/addresses", StaticFiles(directory="addresses"), name="addresses")


@app.exception_handler(404)
async def exception_handler_404(request: Request, exc: Exception):

    return app.templates.TemplateResponse(
        "base/error.html",
        {
            "env": request.app.env,
            "request": request,
            "error": "Can't find the page you are looking for!",
        },
    )


@app.exception_handler(500)
async def exception_handler_500(request: Request, exc: Exception):

    return app.templates.TemplateResponse(
        "base/error.html",
        {
            "env": request.app.env,
            "request": request,
            "error": "Something's not quite right!",
        },
    )


origins = [
    "http://127.0.0.1:8000",
    "https://127.0.0.1:8000",
    # "http://dev.concordium-explorer.nl",
    # "https://dev.concordium-explorer.nl",
    # "http://concordium-explorer.nl",
    # "https://concordium-explorer.nl",
    "http://ccdexplorer.io",
    "https://ccdexplorer.io",
    "http://dev.ccdexplorer.io",
    "https://dev.ccdexplorer.io",
    "https://v2.ccdexplorer.io",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(home.router)
app.include_router(transaction.router)
app.include_router(block.router)
app.include_router(account.router)
app.include_router(account_validator.router)
app.include_router(account_pool.router)
app.include_router(node.router)
app.include_router(smart_contracts.router)
app.include_router(tools.router)
app.include_router(projects.router)
app.include_router(usersv2.router)
app.include_router(statistics.router)
app.include_router(tokens.router)
app.include_router(nodes.router)
app.include_router(staking.router)


@scheduler.scheduled_job("interval", seconds=3, args=[app])
async def repeated_task_get_blocks_and_transactions(app: FastAPI):
    for net in ["mainnet", "testnet"]:

        api_result = await get_url_from_api(
            f"{app.api_url}/v2/{net}/blocks/last/50", app.httpx_client
        )
        app.blocks_cache[net] = api_result.return_value if api_result.ok else None

        api_result = await get_url_from_api(
            f"{app.api_url}/v2/{net}/transactions/last/50", app.httpx_client
        )
        app.transactions_cache[net] = api_result.return_value if api_result.ok else None


@scheduler.scheduled_job("interval", seconds=60, args=[app])
async def repeated_task_get_accounts_id_providers(app: FastAPI):
    for net in ["mainnet", "testnet"]:
        api_result = await get_url_from_api(
            f"{app.api_url}/v2/{net}/accounts/last/50", app.httpx_client
        )
        app.accounts_cache[net] = api_result.return_value if api_result.ok else None

        api_result = await get_url_from_api(
            f"{app.api_url}/v2/{net}/misc/identity-providers",
            app.httpx_client,
        )
        app.identity_providers_cache[net] = (
            api_result.return_value if api_result.ok else None
        )
        if app.accounts_cache[net]:
            for account_ in app.accounts_cache[net]:
                account_info: CCD_AccountInfo = CCD_AccountInfo(
                    **account_["account_info"]
                )
                if account_info.address[:29] not in app.addresses_to_indexes[net]:
                    print(f"Adding {account_info.index} to cache... FROM SCHEDULE")
                    add_account_info_to_cache(account_info, app, net)
