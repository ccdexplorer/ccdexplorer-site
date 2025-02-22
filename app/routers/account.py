import datetime as dt

import httpx
import plotly.express as px
from pydantic import BaseModel
import polars as polars
from ccdexplorer_fundamentals.credential import Identity
from ccdexplorer_fundamentals.cis import MongoTypeTokensTag
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_BlockInfo,
    CCD_AccountInfo,
    CCD_ContractAddress,
    CCD_BlockItemSummary,
)
from app.classes.sankey import SanKey
from ccdexplorer_fundamentals.user_v2 import UserV2
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response, RedirectResponse

from app.classes.dressingroom import (
    MakeUp,
    MakeUpRequest,
    RequestingRoute,
)
from app.env import environment

from app.jinja2_helpers import templates
from app.state import get_httpx_client, get_labeled_accounts, get_user_detailsv2
from app.utils import (
    PaginationRequest,
    account_link,
    calculate_skip,
    pagination_calculator,
    ccdexplorer_plotly_template,
    add_account_info_to_cache,
    from_address_to_index,
    get_url_from_api,
)
import plotly.graph_objects as go

router = APIRouter()


@router.post("/{net}/account/apy-graph/{index_or_hash}", response_class=Response)
async def account_apy_graph(
    request: Request,
    net: str,
    index_or_hash: int | str,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
    tags: dict = Depends(get_labeled_accounts),
):
    theme = "dark"
    body = await request.body()
    if body:
        theme = body.decode("utf-8").split("=")[1]

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{index_or_hash}/apy-data",
        httpx_client,
    )
    result = api_result.return_value if api_result.ok else None
    if not result:
        return None

    if result:
        if "d30_apy_dict" in result:
            d30_apy_dict = (
                {k: v["apy"] for k, v in result["d30_apy_dict"].items()}
                if result["d30_apy_dict"] is not None
                else None
            )
        else:
            d30_apy_dict = None
        if "d90_apy_dict" in result:
            d90_apy_dict = (
                {k: v["apy"] for k, v in result["d90_apy_dict"].items()}
                if result["d90_apy_dict"] is not None
                else None
            )
        else:
            d90_apy_dict = None
        if "d180_apy_dict" in result:
            d180_apy_dict = (
                {k: v["apy"] for k, v in result["d180_apy_dict"].items()}
                if result["d180_apy_dict"] is not None
                else None
            )
        else:
            d180_apy_dict = None

        if d30_apy_dict:
            df_30d = polars.from_dict(d30_apy_dict).melt()
            df_30d.columns = ["date", "30d"]
        if d90_apy_dict:
            df_90d = polars.from_dict(d90_apy_dict).melt()
            df_90d.columns = ["date", "90d"]
        if d180_apy_dict:
            df_180d = polars.from_dict(d180_apy_dict).melt()
            df_180d.columns = ["date", "180d"]

        if d180_apy_dict:

            df = df_180d.join(
                df_30d.join(df_90d, on="date", how="outer_coalesce"),
                on="date",
                how="outer_coalesce",
            ).melt(id_vars="date")

        elif d90_apy_dict:
            df = df_30d.join(df_90d, on="date", how="outer_coalesce").melt(
                id_vars="date"
            )

        elif d30_apy_dict:
            df = df_30d.melt(id_vars="date")

        else:
            df = None

        days_alive = (
            dt.datetime.now() - dt.datetime(2022, 6, 24, 9, 0, 0)
        ).total_seconds() / (60 * 60 * 24)

        domain_pd = polars.Series(
            [
                dt.datetime(2022, 6, 24) + dt.timedelta(days=x)
                for x in range(0, int(days_alive) + 1)
            ]
        ).to_list()

        if df is None:
            return None

        df = df.rename({"variable": "APY period"})

        rng = [
            "#AE7CF7",
            "#70B785",
            "#6E97F7",
        ]
        fig = px.scatter(
            df,
            x="date",
            y="value",
            color="APY period",
            color_discrete_sequence=rng,
            template=ccdexplorer_plotly_template(theme),
        )
        fig.update_yaxes(
            title_text=None,
            showgrid=False,
            linewidth=0,
            zerolinecolor="rgba(0,0,0,0)",
        )
        fig.update_traces(mode="lines")
        fig.update_xaxes(
            title=None,
            type="date",
            showgrid=False,
            range=[domain_pd[0], domain_pd[-1]],
            linewidth=0,
            zerolinecolor="rgba(0,0,0,0)",
        )
        fig.update_layout(
            height=250,
            # width=320,
            legend=dict(orientation="h"),
            title=(
                "Moving Averages for Delegator APY"
                if str(index_or_hash).isnumeric()
                else "Moving Averages for Account APY</sup>"
            ),
            legend_y=-0.2,
            # legend_x=0.7,
            margin=dict(l=0, r=0, t=0, b=0),
        )
        html = fig.to_html(
            config={"responsive": True, "displayModeBar": False},
            full_html=False,
            include_plotlyjs=False,
        )

        return html

    else:
        return None


@router.post(
    "/{net}/account/rewards-bucketed/{account_id}/{account_index}",
    response_class=Response,
)
async def account_rewards_bucketed(
    request: Request,
    net: str,
    account_id: str,
    account_index: int,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    theme = "dark"
    body = await request.body()
    if body:
        theme = body.decode("utf-8").split("=")[1]
    if net == "mainnet":
        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/account/{account_id}/staking-rewards-bucketed",
            httpx_client,
        )
        result_pp = api_result.return_value if api_result.ok else None
        if not result_pp:
            return None

        ff = [
            {
                "date": x["date"],
                "Transaction Fees": x["reward"]["transaction_fees"] / 1_000_000,
                "Validation Reward": x["reward"]["baker_reward"] / 1_000_000,
                "Finalization Reward": x["reward"]["finalization_reward"] / 1_000_000,
            }
            for x in result_pp
        ]
        df = polars.DataFrame(ff)
        df = df.with_columns(polars.col("date").str.to_datetime("%Y-%m-%d"))

        if len(df) > 0:
            # df["date"] = polars.Expr.str.to_date(df["date"])

            df_group = (
                df.sort("date")
                .group_by_dynamic(
                    "date", every="1mo", period="1mo", offset="0mo", closed="right"
                )
                .agg(
                    [
                        polars.sum("Transaction Fees"),
                        polars.sum("Validation Reward"),
                        polars.sum("Finalization Reward"),
                    ]
                )
            )

            melt = df_group.unpivot(
                index=["date"],  # Identifier column(s) to keep
                on=[
                    "Transaction Fees",
                    "Validation Reward",
                    "Finalization Reward",
                ],  # Columns to unpivot
                variable_name="Reward Type",  # Name of the variable column
                value_name="Value",  # Name of the value column
            )

            rng = [
                "#AE7CF7",
                "#70B785",
                "#6E97F7",
            ]
            fig = px.bar(
                melt,
                x="date",
                y="Value",  # order of fitted polynomial,
                color="Reward Type",
                color_discrete_sequence=rng,
                template=ccdexplorer_plotly_template(theme),
            )
            fig.update_yaxes(
                title_text=None,
                showgrid=False,
                linewidth=0,
                zerolinecolor="rgba(0,0,0,0)",
            )
            # fig.update_traces(mode="lines")
            fig.update_xaxes(
                title=None,
                type="date",
                showgrid=False,
                linewidth=0,
                zerolinecolor="rgba(0,0,0,0)",
            )
            fig.update_layout(
                height=250,
                # width=320,
                legend_y=-0.25,
                title=f"Rewards from staking/delegation per month<br>Account {account_index}",
                # title_y=0.46,
                legend=dict(orientation="h"),
                # legend_x=0.7,
                margin=dict(l=0, r=0, t=0, b=0),
            )
            if "last_requests" not in request.state._state:
                request.state.last_requests = {}
            html = fig.to_html(
                config={"responsive": True, "displayModeBar": False},
                full_html=False,
                include_plotlyjs=False,
            )

            return html
        else:
            return ""
    else:
        return ""


@router.get(
    "/{net}/account/{index_or_hash}", response_class=HTMLResponse | RedirectResponse
)
async def get_account(
    request: Request,
    net: str,
    index_or_hash: int | str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    request.state.api_calls = {}
    if "hx-request" in request.headers:
        print("hx-request", request.headers["hx-request"])
    user: UserV2 = await get_user_detailsv2(request)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{index_or_hash}/info",
        httpx_client,
    )
    account_info = CCD_AccountInfo(**api_result.return_value) if api_result.ok else None
    if not account_info:
        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/smart-wallet/public-key/{index_or_hash}",
            httpx_client,
        )
        public_key_info = api_result.return_value if api_result.ok else None
        if not public_key_info:
            error = f"Can't find the account at {index_or_hash} on {net}."
            return templates.TemplateResponse(
                "base/error.html",
                {
                    "request": request,
                    "error": error,
                    "env": environment,
                    "net": net,
                },
            )
        else:
            wallet_contract = CCD_ContractAddress.from_str(
                public_key_info["wallet_contract_address"]
            )
            url = f"/{net}/smart-wallet/{wallet_contract.index}/{wallet_contract.subindex}/{public_key_info['public_key']}"
            response = RedirectResponse(url, status_code=303)
            return response

    # add to address_to_indexes cache if not already there.
    if account_info.address[:29] not in request.app.addresses_to_indexes[net]:
        print(f"Adding {account_info.index} to cache...")
        add_account_info_to_cache(account_info, request.app, net)

    account_id = account_info.address
    account_index = account_info.index

    if account_info.stake:
        delegation = account_info.stake.delegator
        validator_id = (
            account_info.stake.baker.baker_info.baker_id
            if account_info.stake.baker
            else None
        )
    else:
        delegation = None
        validator_id = None

    identity = Identity(account_info)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/misc/identity-providers",
        httpx_client,
    )
    identity_providers = api_result.return_value if api_result.ok else None

    account_link_found = account_link(account_id, net, user, tags, request.app)

    delegation_target_address = None
    account_apy_object = None
    if delegation:
        delegation_target_address = delegation.target
        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/account/{account_id}/staking-rewards-object",
            httpx_client,
        )
        account_apy_object = api_result.return_value if api_result.ok else None

    if validator_id:
        account_is_validator = True

        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/account/{validator_id}/pool-info",
            httpx_client,
        )
        pool = api_result.return_value if api_result.ok else None

        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/account/{account_index}/node", httpx_client
        )
        node = api_result.return_value if api_result.ok else None

        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/account/{validator_id}/earliest-win-time",
            httpx_client,
        )
        earliest_win_time = api_result.return_value if api_result.ok else None

        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/account/{validator_id}/staking-rewards-object",
            httpx_client,
        )
        pool_apy_object = api_result.return_value if api_result.ok else None

        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/account/{account_id}/staking-rewards-object",
            httpx_client,
        )
        account_apy_object = api_result.return_value if api_result.ok else None

    else:

        account_is_validator = False
        pool = None
        node = None
        pool_apy_object = None
        earliest_win_time = None

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{account_id}/rewards-available",
        httpx_client,
    )
    rewards_for_account_available = api_result.return_value if api_result.ok else None

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{account_id}/tokens-available",
        httpx_client,
    )
    tokens_available = api_result.return_value if api_result.ok else None

    tokens_value_USD = 0
    if tokens_available:
        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/account/{account_id}/fungible-tokens/USD",
            httpx_client,
        )
        tokens_value_USD = api_result.return_value if api_result.ok else 0

    ccd_balance_USD = 0
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{account_id}/balance/USD",
        httpx_client,
    )
    ccd_balance_USD = api_result.return_value if api_result.ok else 0

    # TODO
    cns_domains_list = None  # cns_domains_registered(account_id)

    token_ids = []
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{account_id}/token-symbols-for-flow",
        httpx_client,
    )
    token_ids = api_result.return_value if api_result.ok else []

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{account_id}/aliases-in-use",
        httpx_client,
    )
    aliases_in_use = api_result.return_value if api_result.ok else []

    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{account_id}/deployed",
        httpx_client,
    )

    deployed_in_genesis_block = False
    genesis_block_slot_time = None
    if (api_result.ok) and (api_result.return_value is None):
        # this account was created in the genesis block!
        deployed_in_genesis_block = True
        tx_deployed = None
        api_result = api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/block/0",
            httpx_client,
        )
        genesis_block_slot_time = (
            CCD_BlockInfo(**api_result.return_value).slot_time
            if api_result.ok
            else dt.datetime.now().astimezone(dt.UTC)
        )
    else:
        tx_deployed = (
            CCD_BlockItemSummary(**api_result.return_value) if api_result.ok else None
        )

    request.state.api_calls["Account Info"] = (
        f"{request.app.api_url}/docs#/Account/get_account_info_v2__net__account__index_or_hash__info_get"
    )
    request.state.api_calls["Identity Providers"] = (
        f"{request.app.api_url}/docs#/Misc/get_identity_providers_v2__net__misc_identity_providers_get"
    )
    request.state.api_calls["Account Transactions"] = (
        f"{request.app.api_url}/docs#/Account/get_account_txs_v2__net__account__account_id__transactions__skip___limit__get"
    )
    request.state.api_calls["Rewards Available"] = (
        f"{request.app.api_url}/docs#/Account/get_bool_account_rewards_available_v2__net__account__account_id__rewards_available_get"
    )
    request.state.api_calls["APY Data"] = (
        f"{request.app.api_url}/docs#/Account/get_account_apy_data_v2__net__account__index_or_hash__apy_data_get"
    )
    request.state.api_calls["Tokens Available"] = (
        f"{request.app.api_url}/docs#/Account/get_account_tokens_available_v2__net__account__account_address__tokens_available_get"
    )
    request.state.api_calls["CCD Balance in USD"] = (
        f"{request.app.api_url}/docs#/Account/get_account_balance_in_USD_v2__net__account__account_address__balance_USD_get"
    )
    request.state.api_calls["Token Symbols for Flow"] = (
        f"{request.app.api_url}/docs#/Account/get_account_token_symbols_for_flow_v2__net__account__account_address__token_symbols_for_flow_get"
    )
    request.state.api_calls["Verified Fungible Tokens"] = (
        f"{request.app.api_url}/docs#/Account/get_account_fungible_tokens_verified_v2__net__account__account_address__fungible_tokens__skip___limit__verified_get"
    )
    request.state.api_calls["Verified Non-Fungible Tokens"] = (
        f"{request.app.api_url}/docs#/Account/get_account_non_fungible_tokens_verified_v2__net__account__account_address__non_fungible_tokens__skip___limit__verified_get"
    )
    request.state.api_calls["Unverified Tokens"] = (
        f"{request.app.api_url}/docs#/Account/get_account_tokens_unverified_v2__net__account__account_address__tokens__skip___limit__unverified_get"
    )
    request.state.api_calls["Aliases in Use"] = (
        f"{request.app.api_url}/docs#/Account/get_aliases_in_use_for_account_v2__net__account__account_address__aliases_in_use_get"
    )
    request.state.api_calls["Deployed Tx"] = (
        f"{request.app.api_url}/docs#/Account/get_account_deployment_tx_v2__net__account__account_id__deployed_get"
    )
    request.state.api_calls["Transactions for Flow"] = (
        f"{request.app.api_url}/docs#/Account/get_account_transactions_for_flow_graph_v2__net__account__account_id__transactions_for_flow__gte___start_date___end_date__get"
    )
    request.state.api_calls["Rewards for Flow"] = (
        f"{request.app.api_url}/docs#/Account/get_account_rewards_for_flow_graph_v2__net__account__account_id__rewards_for_flow__start_date___end_date__get"
    )
    request.state.api_calls["Pool Info"] = (
        f"{request.app.api_url}/docs#/Account/get_validator_pool_info_v2__net__account__index__pool_info_get"
    )
    request.state.api_calls["Node"] = (
        f"{request.app.api_url}/docs#/Account/get_account_validator_node_v2__net__account__index__node_get"
    )
    request.state.api_calls["Earliest Win Time"] = (
        f"{request.app.api_url}/docs#/Account/get_validator_earliest_win_time_v2__net__account__index__earliest_win_time_get"
    )
    request.state.api_calls["Current Payday Stats"] = (
        f"{request.app.api_url}/docs#/Account/get_validator_current_payday_stats_v2__net__account__index__current_payday_stats_get"
    )
    request.state.api_calls["Validator/Account Staking Rewards"] = (
        f"{request.app.api_url}/docs#/Account/get_staking_rewards_object_v2__net__account__index_or_hash__staking_rewards_object_get"
    )

    request.state.api_calls["Pool Delegators"] = (
        f"{request.app.api_url}/docs#/Account/get_account_pool_delegators_v2__net__account__index__pool_delegators__skip___limit__get"
    )
    request.state.api_calls["Validator Tally"] = (
        f"{request.app.api_url}/docs#/Account/get_validator_tally_v2__net__account__index__validator_tally__skip___limit__get"
    )
    request.state.api_calls["Validator Transactions"] = (
        f"{request.app.api_url}/docs#/Account/get_account_validator_txs_v2__net__account__account_id__validator_transactions__skip___limit__get"
    )

    request.state.api_calls["Staking Rewards"] = (
        f"{request.app.api_url}/docs#/Account/get_staking_rewards_bucketed_v2__net__account__account_id__staking_rewards_bucketed_get"
    )
    request.state.api_calls["Validator Performance"] = (
        f"{request.app.api_url}/docs#/Account/get_validator_performance_v2__net__account__index__validator_performance_get"
    )
    # TODO
    exchange_rates = {"CCD": {"rate": 1}}
    return templates.TemplateResponse(
        "account/account_account.html",
        {
            "env": request.app.env,
            "rewards_no_stake": (account_info.stake.baker is None)
            and (account_info.stake.delegator is None)
            and rewards_for_account_available,
            "rewards_for_account_available": rewards_for_account_available,
            "account_id": account_id,
            "account_index": account_index,
            "token_ids_for_flow": token_ids,
            "tx_deployed": tx_deployed,
            "deployed_in_genesis_block": deployed_in_genesis_block,
            "genesis_block_slot_time": genesis_block_slot_time,
            "request": request,
            "exchange_rates": exchange_rates,
            "tokens_value_USD": tokens_value_USD,
            "ccd_balance_USD": ccd_balance_USD,
            "pool_apy_object": pool_apy_object,
            "account_apy_object": account_apy_object,
            "account": account_info,
            "pool": pool,
            "earliest_win_time": earliest_win_time,
            "node": node,
            "aliases_in_use": aliases_in_use,
            "account_is_validator": account_is_validator,
            "cns_domains_list": cns_domains_list,
            "identity": identity,
            "identity_providers": identity_providers,
            # "recurring": recurring,
            "delegation": delegation,
            "delegation_target_address": delegation_target_address,
            "net": net,
            "user": user,
            "tags": tags,
            "account_link_found": account_link_found,
            # "tag_found": tag_found,
            # "tag_label": tag_label,
            "tokens_available": tokens_available,
        },
    )


class SanKeyParams(BaseModel):
    theme: str
    gte: str | int
    start_date: str
    end_date: str
    token: str


@router.post(
    "/ajax_sankey/{net}/{account_id}",
    response_class=HTMLResponse,
)
async def request_sankey(
    request: Request,
    net: str,
    account_id: str,
    post_params: SanKeyParams,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    user: UserV2 = await get_user_detailsv2(request)
    theme = post_params.theme
    gte = post_params.gte
    start_date = post_params.start_date
    end_date = post_params.end_date
    token = post_params.token

    if net == "testnet":
        return "Not available on testnet."
    if isinstance(gte, str):
        gte = int(gte.replace(",", "").replace(".", ""))

    sankey = SanKey(account_id, gte, request.app, net, token)
    if token == "CCD":
        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/account/{account_id}/transactions-for-flow/{gte}/{start_date}/{end_date}",
            httpx_client,
        )
        txs_for_account = api_result.return_value if api_result.ok else []

        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/account/{account_id}/rewards-for-flow/{start_date}/{end_date}",
            httpx_client,
        )
        account_rewards_total = api_result.return_value if api_result.ok else 0

        sankey.add_txs_for_account(
            txs_for_account, account_rewards_total  # , exchange_rates
        )

    else:
        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/token/{token}/info",
            httpx_client,
        )
        token_tag = (
            MongoTypeTokensTag(**api_result.return_value) if api_result.ok else None
        )
        if not token_tag:
            return None

        token_id = (
            f"{token_tag.contracts[0]}-"
            if token != "CCDOGE"
            else f"{token_tag.contracts[0]}-01"
        )

        decimals = token_tag.decimals
        display_name = token_tag.display_name

        api_result = await get_url_from_api(
            f"{request.app.api_url}/v2/{net}/account/{account_id}/token-transactions-for-flow/{token_id}/{gte}/{start_date}/{end_date}",
            httpx_client,
        )
        txs_for_account = api_result.return_value if api_result.ok else []

        sankey.add_txs_for_account_for_token(txs_for_account, decimals, display_name)
        pass
    account_ids_to_lookup = {
        x[:29]: from_address_to_index(x[:29], net, request.app)
        for x in sankey.labels.keys()
        if len(x) > 28
    }

    await sankey.cross_the_streams(user, tags, account_ids_to_lookup)

    fig = go.Figure(
        data=[
            go.Sankey(
                node=dict(
                    pad=25,
                    thickness=10,
                    line=dict(color="grey", width=1.0),
                    label=sankey.tagged_labels,
                    color=sankey.colors,
                ),
                link=dict(
                    source=sankey.source,
                    target=sankey.target,
                    value=sankey.value,
                    color=sankey.colors,
                ),
            )
        ],
    )
    fig.update_traces(node_hoverlabel_font_shadow="auto", selector=dict(type="sankey"))
    fig.update_layout(
        template=ccdexplorer_plotly_template(theme),
        title_text=f"Flow diagram for account for token {token}",
        font_size=10,
    )

    sankey_html = fig.to_html(
        config={"responsive": True, "displayModeBar": False},
        full_html=False,
        include_plotlyjs=False,
    )

    return templates.TemplateResponse(
        "account/account_graph_table.html",
        {
            "env": request.app.env,
            "request": request,
            "user": user,
            "net": net,
            "account_id": account_id,
            "token": token,
            "sankey_html": sankey_html,
            "graph_dict": sankey.graph_dict,
            "tags": tags,
            "app": request.app,
        },
    )


@router.get(
    "/account_transactions/{net}/{account_id}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def get_account_transactions(
    request: Request,
    net: str,
    account_id: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
    # recurring: Recurring = Depends(get_recurring),
    tags: dict = Depends(get_labeled_accounts),
):
    """
    Add {net}.
    """
    limit = 20
    user: UserV2 = await get_user_detailsv2(request)

    skip = calculate_skip(requested_page, total_rows, limit)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{account_id}/transactions/{skip}/{limit}",
        httpx_client,
    )
    tx_result = api_result.return_value if api_result.ok else None
    if not tx_result:
        error = (
            f"Request error getting transactions for account at {account_id} on {net}."
        )
        return templates.TemplateResponse(
            "base/error-request.html",
            {
                "request": request,
                "error": error,
                "env": environment,
                "net": net,
            },
        )

    tx_result_transactions = tx_result["transactions"]
    total_rows = tx_result["total_tx_count"]
    # made_up_txs = []
    # if len(tx_result_transactions) > 0:
    #     for transaction in tx_result_transactions:
    #         transaction = CCD_BlockItemSummary(**transaction)
    #         makeup_request = MakeUpRequest(
    #             **{
    #                 "net": net,
    #                 "httpx_client": httpx_client,
    #                 "tags": tags,
    #                 "user": user,
    #                 "app": request.app,
    #                 "requesting_route": RequestingRoute.account,
    #             }
    #         )

    #         classified_tx = await MakeUp(
    #             makeup_request=makeup_request
    #         ).prepare_for_display(transaction, "", False)
    #         made_up_txs.append(classified_tx)

    pagination_request = PaginationRequest(
        total_txs=total_rows,
        requested_page=requested_page,
        word="tx",
        action_string="tx",
        limit=limit,
    )
    pagination = pagination_calculator(pagination_request)
    # html = templates.get_template("account/account_transactions.html").render(
    #     {
    #         "transactions": made_up_txs,
    #         "tags": tags,
    #         "net": net,
    #         "request": request,
    #         "pagination": pagination,
    #         "totals_in_pagination": True,
    #         "total_rows": total_rows,
    #     }
    # )

    html = templates.get_template("base/transactions_simple_list.html").render(
        {
            "transactions": [CCD_BlockItemSummary(**x) for x in tx_result_transactions],
            "tags": tags,
            "user": user,
            "net": net,
            "request": request,
            "pagination": pagination,
            "totals_in_pagination": True,
            "total_rows": total_rows,
        }
    )

    return html


def collapse_tokens_from_aliases_fungible(tokens: list):
    collaped_tokens = {}
    if tokens:
        for token in tokens:
            if token["token_address"] not in collaped_tokens:
                collaped_tokens[token["token_address"]] = token
            else:
                collaped_tokens[token["token_address"]]["token_amount"] = str(
                    int(collaped_tokens[token["token_address"]]["token_amount"])
                    + int(token["token_amount"])
                )
                collaped_tokens[token["token_address"]]["token_value"] = (
                    collaped_tokens[token["token_address"]]["token_value"]
                    + token["token_value"]
                )

                collaped_tokens[token["token_address"]]["token_value_USD"] = (
                    collaped_tokens[token["token_address"]]["token_value_USD"]
                    + token["token_value_USD"]
                )

    return collaped_tokens


def collapse_tokens_from_aliases_non_fungible(tokens: list):
    collaped_tokens = {}
    if tokens:
        for token in tokens:
            if token["token_address"] not in collaped_tokens:
                collaped_tokens[token["token_address"]] = token
            else:
                collaped_tokens[token["token_address"]]["token_amount"] = str(
                    int(collaped_tokens[token["token_address"]]["token_amount"])
                    + int(token["token_amount"])
                )

    return collaped_tokens


@router.get(
    "/ajax_account_tokens/{net}/fungible-verified/{address}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_tokens_fungible_verified(
    request: Request,
    net: str,
    address: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    limit = 10
    address = address.replace("&lt;", "<").replace("&gt;", ">")
    skip = calculate_skip(requested_page, total_rows, limit)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{address}/fungible-tokens/{skip}/{limit}/verified",
        httpx_client,
    )
    fungible_verified_tokens = (
        api_result.return_value["tokens"] if api_result.ok else None
    )

    fungible_verified_tokens_count = (
        api_result.return_value["total_token_count"] if api_result.ok else 0
    )

    fungible_verified_tokens = collapse_tokens_from_aliases_fungible(
        fungible_verified_tokens
    )
    pagination_request = PaginationRequest(
        total_txs=fungible_verified_tokens_count,
        requested_page=requested_page,
        word="token",
        action_string="f_v_token",
        limit=limit,
    )
    pagination = pagination_calculator(pagination_request)
    html = templates.get_template(
        "account/account_fungible_verified_tokens.html"
    ).render(
        {
            "fungible_verified_tokens": fungible_verified_tokens,
            "tags": tags,
            "net": net,
            "request": request,
            "pagination": pagination,
            "totals_in_pagination": True,
            "total_rows": total_rows,
        }
    )

    return html


@router.get(
    "/ajax_account_tokens/{net}/non-fungible-verified/{address}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_tokens_non_fungible_verified(
    request: Request,
    net: str,
    address: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    limit = 10
    address = address.replace("&lt;", "<").replace("&gt;", ">")
    skip = calculate_skip(requested_page, total_rows, limit)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{address}/non-fungible-tokens/{skip}/{limit}/verified",
        httpx_client,
    )
    non_fungible_verified_tokens = (
        api_result.return_value["tokens"] if api_result.ok else None
    )

    non_fungible_verified_tokens_count = (
        api_result.return_value["total_token_count"] if api_result.ok else 0
    )

    non_fungible_verified_tokens = collapse_tokens_from_aliases_non_fungible(
        non_fungible_verified_tokens
    )
    pagination_request = PaginationRequest(
        total_txs=non_fungible_verified_tokens_count,
        requested_page=requested_page,
        word="token",
        action_string="n_f_v_token",
        limit=limit,
    )
    pagination = pagination_calculator(pagination_request)
    html = templates.get_template(
        "account/account_non_fungible_verified_tokens.html"
    ).render(
        {
            "non_fungible_verified_tokens": non_fungible_verified_tokens,
            "tags": tags,
            "net": net,
            "request": request,
            "pagination": pagination,
            "totals_in_pagination": True,
            "total_rows": total_rows,
        }
    )

    return html


@router.get(
    "/ajax_account_tokens/{net}/unverified/{address}/{requested_page}/{total_rows}/{api_key}",
    response_class=HTMLResponse,
)
async def get_ajax_tokens_unverified(
    request: Request,
    net: str,
    address: str,
    requested_page: int,
    total_rows: int,
    api_key: str,
    tags: dict = Depends(get_labeled_accounts),
    httpx_client: httpx.AsyncClient = Depends(get_httpx_client),
):
    limit = 10
    address = address.replace("&lt;", "<").replace("&gt;", ">")
    skip = calculate_skip(requested_page, total_rows, limit)
    api_result = await get_url_from_api(
        f"{request.app.api_url}/v2/{net}/account/{address}/tokens/{skip}/{limit}/unverified",
        httpx_client,
    )
    unverified_tokens = api_result.return_value["tokens"] if api_result.ok else None

    unverified_tokens = collapse_tokens_from_aliases_non_fungible(unverified_tokens)
    pagination_request = PaginationRequest(
        total_txs=len(unverified_tokens),
        requested_page=requested_page,
        word="token",
        action_string="un_token",
        limit=limit,
    )
    pagination = pagination_calculator(pagination_request)
    html = templates.get_template("account/account_unverified_tokens.html").render(
        {
            "unverified_tokens": unverified_tokens,
            "tags": tags,
            "net": net,
            "request": request,
            "pagination": pagination,
            "totals_in_pagination": True,
            "total_rows": total_rows,
        }
    )

    return html
