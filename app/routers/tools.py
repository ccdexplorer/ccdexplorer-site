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


async def get_data_for_chain_transactions_for_dates(
    app, start_date: str, end_date: str
) -> list[str]:
    api_result = await get_url_from_api(
        f"{app.api_url}/v2/mainnet/misc/statistics-chain/{start_date}/{end_date}",
        app.httpx_client,
    )
    result = api_result.return_value if api_result.ok else []
    return result


@router.get(
    "/{net}/tools/labeled-accounts", response_class=HTMLResponse | RedirectResponse
)
async def labeled_accounts(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    # tags_community: dict = Depends(get_community_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/misc/projects/all-ids",
        httpx_client,
    )
    projects = api_result.return_value if api_result.ok else []
    if net == "mainnet":
        return templates.TemplateResponse(
            "/tools/labeled-accounts.html",
            {
                "env": environment,
                "request": request,
                "user": user,
                "tags": tags,
                "projects": projects,
                "net": net,
            },
        )
    else:
        response = RedirectResponse(
            url="/mainnet/tools/labeled-accounts", status_code=302
        )
        return response
