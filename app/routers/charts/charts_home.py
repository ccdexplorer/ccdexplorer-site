import httpx
from ccdexplorer_fundamentals.user_v2 import UserV2
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.env import environment
from app.jinja2_helpers import templates
from app.state import get_httpx_client, get_labeled_accounts, get_user_detailsv2

router = APIRouter()


@router.get("/{net}/charts", response_class=HTMLResponse)
async def get_charts_home(
    request: Request,
    net: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    request.state.api_calls = {}

    user: UserV2 = await get_user_detailsv2(request)
    return templates.TemplateResponse(
        "charts/charts_home.html",
        {
            "request": request,
            "net": net,
            "tags": tags,
            "user": user,
            "env": environment,
        },
    )
