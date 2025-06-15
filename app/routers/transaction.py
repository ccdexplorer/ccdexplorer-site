from ccdexplorer_fundamentals.user_v2 import UserV2
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import CCD_BlockItemSummary
from app.jinja2_helpers import templates
from app.env import environment
from app.classes.dressingroom import MakeUp, MakeUpRequest, RequestingRoute
from app.state import get_labeled_accounts, get_user_detailsv2, get_httpx_client
from app.utils import tx_type_translation, get_url_from_api
import httpx

router = APIRouter()


@router.get("/{net}/transaction/{tx_hash}", response_class=HTMLResponse)
async def get_transaction(
    request: Request,
    net: str,
    tx_hash: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    request.state.api_calls = {}

    user: UserV2 | None = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/transaction/{tx_hash}", httpx_client
    )
    result = CCD_BlockItemSummary(**api_result.return_value) if api_result.ok else None
    if not result:
        error = f"Can't find the transaction at {tx_hash} on {net}."
        return templates.TemplateResponse(
            "base/error.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )

    makeup_request = MakeUpRequest(
        **{
            "net": net,
            "httpx_client": httpx_client,
            "tags": tags,
            "user": user,
            "ccd_historical": None,
            "app": request.app,
            "requesting_route": RequestingRoute.transaction,
        }
    )
    classified_tx = await MakeUp(makeup_request=makeup_request).prepare_for_display(
        result, "", False
    )
    tx_with_makeup = classified_tx.dct
    request.state.api_calls["Transaction Info"] = (
        f"{request.app.api_url}/docs#/Transaction/get_transaction_v2__net__transaction__tx_hash__get"
    )
    return templates.TemplateResponse(
        "tx/tx.html",
        {
            "request": request,
            "tx": result,
            "net": net,
            "tx_with_makeup": tx_with_makeup,
            "tags": tags,
            "user": user,
            "env": environment,
            "tx_type_translation": tx_type_translation,
            "tx_hash": tx_hash,
            "transaction": result,
            "status": "finalized",
            "block_hash": result.block_info.hash,
            "cns_domain_name": classified_tx.cns_domain.domain_name,
            "events_list": classified_tx.events_list,
            "cns_tx_message": classified_tx.cns_domain.action,
            "classified_tx": classified_tx,
        },
    )
