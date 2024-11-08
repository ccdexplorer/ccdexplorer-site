import datetime as dt
from functools import lru_cache
import io
import math
import typing
from datetime import timedelta
from enum import Enum
from typing import Any, Optional
from fastapi import Request, FastAPI
import dateutil
import httpx
import plotly.graph_objects as go
from ccdexplorer_fundamentals.cis import (
    CIS,
    LoggedEvents,
    MongoTypeTokenAddress,
    MongoTypeTokensTag,
    TokenMetaData,
)
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import (
    CCD_ContractAddress,
    CCD_AccountInfo,
    CCD_RejectReason,
    CCD_UpdatePayload,
)
from ccdexplorer_fundamentals.mongodb import Collections, MongoMotor
from ccdexplorer_fundamentals.user_v2 import UserV2
from pydantic import BaseModel

import base64
import json
from ccdexplorer_schema_parser.Schema import Schema


class TypeContentsCategories(Enum):
    transfer = "Transfers"
    smart_contract = "Smart Cts"
    data_registered = "Data"
    staking = "Staking"
    identity = "Identity"
    chain = "Chain"
    rejected = "Rejected"


class TypeContentsCategoryColors(Enum):
    transfer = ("#33C364",)
    smart_contract = ("#E87E90", "#7939BA", "#B37CDF")
    data_registered = ("#48A2AE",)
    staking = ("#8BE7AA",)
    identity = ("#F6DB9A",)
    chain = ("#FFFDE4",)
    rejected = ("#DC5050",)


class TypeContents(BaseModel):
    display_str: str
    category: TypeContentsCategories
    color: str


tx_type_translation = {}
# smart contracts
tx_type_translation["module_deployed"] = TypeContents(
    display_str="new module",
    category=TypeContentsCategories.smart_contract,
    color=TypeContentsCategoryColors.smart_contract.value[0],
)
tx_type_translation["contract_initialized"] = TypeContents(
    display_str="new contract",
    category=TypeContentsCategories.smart_contract,
    color=TypeContentsCategoryColors.smart_contract.value[1],
)
tx_type_translation["contract_update_issued"] = TypeContents(
    display_str="contract updated",
    category=TypeContentsCategories.smart_contract,
    color=TypeContentsCategoryColors.smart_contract.value[2],
)

# account transfer
tx_type_translation["account_transfer"] = TypeContents(
    display_str="transfer",
    category=TypeContentsCategories.transfer,
    color=TypeContentsCategoryColors.transfer.value[0],
)
tx_type_translation["transferred_with_schedule"] = TypeContents(
    display_str="scheduled transfer",
    category=TypeContentsCategories.transfer,
    color=TypeContentsCategoryColors.transfer.value[0],
)

# staking
tx_type_translation["baker_added"] = TypeContents(
    display_str="validator added",
    category=TypeContentsCategories.staking,
    color=TypeContentsCategoryColors.staking.value[0],
)

tx_type_translation["baker_removed"] = TypeContents(
    display_str="validator removed",
    category=TypeContentsCategories.staking,
    color=TypeContentsCategoryColors.staking.value[0],
)

tx_type_translation["baker_stake_updated"] = TypeContents(
    display_str="validator updated",
    category=TypeContentsCategories.staking,
    color=TypeContentsCategoryColors.staking.value[0],
)

tx_type_translation["baker_restake_earnings_updated"] = TypeContents(
    display_str="validator updated",
    category=TypeContentsCategories.staking,
    color=TypeContentsCategoryColors.staking.value[0],
)

tx_type_translation["baker_restake_earnings_updated"] = TypeContents(
    display_str="validator updated",
    category=TypeContentsCategories.staking,
    color=TypeContentsCategoryColors.staking.value[0],
)

tx_type_translation["baker_keys_updated"] = TypeContents(
    display_str="validator updated",
    category=TypeContentsCategories.staking,
    color=TypeContentsCategoryColors.staking.value[0],
)

tx_type_translation["baker_configured"] = TypeContents(
    display_str="validator configured",
    category=TypeContentsCategories.staking,
    color=TypeContentsCategoryColors.staking.value[0],
)

tx_type_translation["delegation_configured"] = TypeContents(
    display_str="delegation configured",
    category=TypeContentsCategories.staking,
    color=TypeContentsCategoryColors.staking.value[0],
)
# credentials
tx_type_translation["credential_keys_updated"] = TypeContents(
    display_str="credentials updated",
    category=TypeContentsCategories.identity,
    color=TypeContentsCategoryColors.identity.value[0],
)

tx_type_translation["credentials_updated"] = TypeContents(
    display_str="credentials updated",
    category=TypeContentsCategories.identity,
    color=TypeContentsCategoryColors.identity.value[0],
)

tx_type_translation["credentials_updated"] = TypeContents(
    display_str="credentials updated",
    category=TypeContentsCategories.identity,
    color=TypeContentsCategoryColors.identity.value[0],
)
# data registered
tx_type_translation["data_registered"] = TypeContents(
    display_str="data registered",
    category=TypeContentsCategories.data_registered,
    color=TypeContentsCategoryColors.data_registered.value[0],
)

# rejected
for reason in CCD_RejectReason.model_fields:
    tx_type_translation[reason] = TypeContents(
        display_str=reason.replace("_", " "),
        category=TypeContentsCategories.rejected,
        color=TypeContentsCategoryColors.rejected.value[0],
    )

payload_translation = {}
payload_translation["protocol_update"] = "protocol"
payload_translation["election_difficulty_update"] = "election difficulty"
payload_translation["euro_per_energy_update"] = "EUR per NRG"
payload_translation["micro_ccd_per_euro_update"] = "CCD per EUR"
payload_translation["foundation_account_update"] = "foundation account"
payload_translation["mint_distribution_update"] = "mint distribution"
payload_translation["transaction_fee_distribution_update"] = "tx fee distribution"
payload_translation["baker_stake_threshold_update"] = "validator stake threshold"
payload_translation["root_update"] = "root"
payload_translation["level_1_update"] = "level 1"
payload_translation["add_anonymity_revoker_update"] = "add anonymity revoker"
payload_translation["add_identity_provider_update"] = "add identity provider"
payload_translation["cooldown_parameters_cpv_1_update"] = "cooldown parameters"
payload_translation["pool_parameters_cpv_1_update"] = "pool parameters"
payload_translation["time_parameters_cpv_1_update"] = "time parameters"
payload_translation["mint_distribution_cpv_1_update"] = "mint distribution"
payload_translation["finalization_committee_parameters_update"] = (
    "finalization committee parameters"
)


# update
for payload in CCD_UpdatePayload.model_fields:
    tx_type_translation[payload] = TypeContents(
        display_str=payload_translation[payload],
        category=TypeContentsCategories.chain,
        color=TypeContentsCategoryColors.chain.value[0],
    )

# identity
tx_type_translation["normal"] = TypeContents(
    display_str="account creation",
    category=TypeContentsCategories.identity,
    color=TypeContentsCategoryColors.identity.value[0],
)

tx_type_translation["initial"] = TypeContents(
    display_str="account creation",
    category=TypeContentsCategories.identity,
    color=TypeContentsCategoryColors.identity.value[0],
)


def tx_type_translator(tx_type_contents: str, request_type: str) -> str:
    result = tx_type_translation.get(tx_type_contents, None)
    if result:
        result: TypeContents
        if request_type == "icon":

            if result.category == TypeContentsCategories.smart_contract:
                icon = f'<i style="color:{result.color};" class="bi bi-card-checklist"></i>'
            elif result.category == TypeContentsCategories.transfer:
                icon = f'<i style="color:{result.color};" class="bi bi-arrow-left-right" text-transfer"></i>'
            elif result.category == TypeContentsCategories.data_registered:
                icon = f'<i style="color:{result.color};" class="bi bi-clipboard-pulse"></i>'
            elif result.category == TypeContentsCategories.identity:
                icon = f'<i  style="color:{result.color};" class="bi bi-bag-plus"></i>'
            elif result.category == TypeContentsCategories.staking:
                icon = f'<i  style="color:{result.color};" class="bi bi-bar-chart-line-fill"></i>'
            elif result.category == TypeContentsCategories.rejected:
                icon = f'<i  style="color:{result.color};" class="bi bi-ban""></i>'
            elif result.category == TypeContentsCategories.chain:
                icon = '<img class="tiny-logo" src="/static/logos/small-logo-grey.png" alt="small-logo" height="16px">'

            return icon
        else:
            return result.display_str


class ProcessEventRequest(BaseModel):
    class Config:
        arbitrary_types_allowed = True

    contract_address: CCD_ContractAddress
    token_metadata: Optional[TokenMetaData] = None
    event: str
    net: str
    user: Optional[UserV2] = None
    tags: Optional[dict] = None
    httpx_client: httpx.AsyncClient
    token_information: Optional[MongoTypeTokensTag] = None
    token_addresses_with_markup: Optional[dict] = None
    app: typing.Any = None


def ccdexplorer_plotly_template(theme: str):
    rng = [
        "#EE9B54",
        "#F7D30A",
        "#6E97F7",
        "#F36F85",
        "#AE7CF7",
        "#508A86",
        "#005B58",
        # "#0E2625",
    ]
    primary_font = "sans-serif, Arial Black"
    ccdexplorer_template = go.layout.Template()
    if theme == "dark":
        paper_bgcolor = "#0A0A0A"
        font_color = "white"
    else:
        paper_bgcolor = "#fff"
        font_color = "black"
    ccdexplorer_template.layout = go.Layout(
        paper_bgcolor=paper_bgcolor,
        plot_bgcolor=paper_bgcolor,
        colorway=rng,
        font_color=font_color,
        font_family=primary_font,
        font_size=18,
        title_font_family=primary_font,
        title_font_size=14,
        title_font_color="grey",
        title_xref="container",
        title_yref="container",
        title_x=0.5,
        title_y=0.96,
        title_xanchor="center",
        title_yanchor="top",
        title_pad_l=0,
        title_pad_r=0,
        title_pad_t=6,
        title_pad_b=0,
        showlegend=True,
        legend_font_family=primary_font,
        legend_font_size=12,
        legend_orientation="v",
        legend_y=-0.52,
        legend_x=0.0,
        legend_title_font_family=primary_font,
        legend_title_font_size=12,
        legend_title_text="",
        legend_bgcolor="rgba(0,0,0,0)",
        margin_l=24,
        margin_r=24,
        margin_t=64,
        margin_b=64,
        margin_pad=0,
        margin_autoexpand=True,
        coloraxis_autocolorscale=False,  # Set to False as otherwise users cannot customize via `color_continous_scale`
        coloraxis_colorbar_outlinewidth=0,
        coloraxis_colorbar_thickness=20,
        coloraxis_colorbar_showticklabels=True,
        coloraxis_colorbar_ticks="outside",
        coloraxis_colorbar_tickwidth=1,
        coloraxis_colorbar_ticklen=8,
        coloraxis_colorbar_tickfont_family=primary_font,
        coloraxis_colorbar_tickfont_size=14,
        coloraxis_colorbar_ticklabelposition="outside",
        coloraxis_colorbar_title_font_family=primary_font,
        coloraxis_colorbar_title_font_size=14,
        bargroupgap=0.1,
        uniformtext_minsize=12,
        uniformtext_mode="hide",
        # X AXIS
        xaxis_visible=True,
        xaxis_title_font_family=primary_font,
        xaxis_title_font_size=12,
        xaxis_title_standoff=8,
        xaxis_ticklabelposition="outside",
        xaxis_ticks="outside",
        xaxis_ticklen=8,
        xaxis_tickwidth=1,
        xaxis_showticklabels=True,
        xaxis_automargin=True,
        xaxis_tickfont_family=primary_font,
        xaxis_tickfont_size=12,
        xaxis_showline=True,
        xaxis_layer="below traces",
        xaxis_linewidth=1,
        xaxis_zeroline=False,
        xaxis_mirror=True,
        # Y AXIS
        yaxis_visible=True,
        yaxis_title_font_family=primary_font,
        yaxis_title_font_size=12,
        yaxis_title_standoff=8,
        yaxis_ticklabelposition="outside",
        yaxis_ticks="outside",
        yaxis_ticklen=8,
        yaxis_tickwidth=1,
        yaxis_showticklabels=True,
        yaxis_automargin=True,
        yaxis_tickfont_family=primary_font,
        yaxis_tickfont_size=12,
        yaxis_showline=True,
        yaxis_layer="below traces",
        yaxis_linewidth=1,
        yaxis_zeroline=False,
        yaxis_mirror=True,
    )

    return ccdexplorer_template


def expectation_view(expectation):
    if expectation < 5:
        expectation_string = f"{expectation:,.2f}"
    else:
        expectation_string = f"{expectation:,.0f}"

    return expectation_string


async def get_all_data_for_analysis_and_project(
    analysis: str, project_id: str, mongomotor: MongoMotor, dates_to_include: list[str]
) -> list[str]:
    pipeline = [
        {"$match": {"date": {"$in": dates_to_include}}},
        {"$match": {"type": analysis}},
        {"$match": {"project": project_id}},
        {"$project": {"_id": 0, "type": 0, "usecase": 0}},
        {"$sort": {"date": 1}},
    ]
    result = (
        await mongomotor.mainnet[Collections.statistics]
        .aggregate(pipeline)
        .to_list(length=None)
    )
    return [x for x in result]


def generate_dates_from_start_until_end(start: str, end: str):
    start_date = dateutil.parser.parse(start)
    end_date = dateutil.parser.parse(end)
    date_range = []

    current_date = start_date
    while current_date <= end_date:
        date_range.append(current_date.strftime("%Y-%m-%d"))
        current_date += timedelta(days=1)

    return date_range


def millify(n):
    millnames = ["", " Thousand", " M", " B", " Tr"]
    n = float(n)
    millidx = max(
        0,
        min(
            len(millnames) - 1, int(math.floor(0 if n == 0 else math.log10(abs(n)) / 3))
        ),
    )

    return "{:.0f}{}".format(n / 10 ** (3 * millidx), millnames[millidx])


def contract_tag(value, user: UserV2 = None, community_labels=None, header=False):
    """ """

    tag_label = None
    tag_found = False

    if not tag_label:
        if community_labels:
            account_labeled = str(value) in community_labels
            if account_labeled:
                tag = community_labels[str(value)]
                tag_label = tag
                account_labeled = True

        # if tags:
        #     tag_found = False
        #     # for label_group in tags["labels"].keys():
        #     label_group = "contracts"
        #     label_group_color = tags["colors"][label_group]
        #     for _id, tag in tags["labels"][label_group].items():
        #         if CCD_ContractAddress.from_str(_id) == value:
        #             tag_label = (
        #                 f"{tag}"
        #                 if not header
        #                 else f'<span style="background-color: {label_group_color}" class="badge rounded-pill ms-5 mt-1"><small>{tag}</small></span>'
        #             )
        #             tag_found = True
        # else:
        #     tag_found = False
        #     tag_label = None

    return tag_found, tag_label


def module_link(value):
    return f'<small><a href="/module/{value}">{value}</a></small>'


def instance_link_v2(
    value: CCD_ContractAddress, user=None, tags=None, net: str = "mainnet"
):
    if isinstance(user, dict):
        user = UserV2(**user)
    tag_found, tag_label = contract_tag(value, user, tags)
    if not tag_found:
        tag_label = f"{(value.to_str())}"
    return f'<a class="sm-text" href="/{net}/instance/{value.index}/{value.subindex}"><i class="bi bi-card-checklist"></i>{tag_label}</a>'


def micro_ccd_display(value: str):
    try:
        amount = int(value) / 1_000_000
    except:  # noqa: E722
        amount = 0
    ccd_amount_str = f"{amount:,.6f}"
    splits = ccd_amount_str.split(".")
    return f'<span class="ccd">Ͼ{splits[0]}</span>.<span class="ccd_decimals">{splits[1]}</span>'


def instance_link_from_str(value: str, net: str, user=None, tags=None):
    if isinstance(user, dict):
        user = UserV2(**user)
    return instance_link_v2(CCD_ContractAddress.from_str(value), user, tags, net)


def uptime(value):
    days = value / (60 * 60 * 24 * 1000)
    if days < 1:
        hours = value / (60 * 60 * 1000)
        if hours < 1:
            min = value / (60 * 1000)
            return f"{min:.0f}m"
        else:
            return f"{hours:.0f}h"
    else:
        return f"{days:.0f}d"


def cost_html(value, energy):
    if energy:
        return f'<small><b>Energy: </b><span class="ccd">{int(value):,.0f}</span> NRG</small>'
    else:
        return f"<small><b>Cost: </b>{micro_ccd_display(value)}</small>"


def token_value_no_decimals(value: str, token: str):
    try:
        amount = int(value)
    except:  # noqa: E722
        amount = 0
    return f'<span class="ccd">{amount:,.0f} {token}</span>'


def datetime_delta_format_schedule_node(value):
    if value:
        delta = dt.datetime.now() - dt.datetime.fromtimestamp(value / 1000)
        return verbose_timedelta(delta)
    else:
        return ""


def datetime_regular(value: dt.datetime):
    return f"{value:%Y-%m-%d %H:%M:%S}"


def datetime_regular_parse(value: str):
    value_parsed = dateutil.parser.parse(value)
    return f"{value_parsed:%Y-%m-%d %H:%M:%S}"


def cooldown_string(value: str):
    value = value.replace("_", " ").lower()
    return value.capitalize()


def datetime_delta_format_since(value: dt.datetime):
    if value:
        delta = dt.datetime.now(dt.timezone.utc) - value.astimezone(dt.timezone.utc)
        return verbose_timedelta(delta)
    else:
        return ""


def datetime_delta_format_since_parse(value: str):
    value_parsed: dt.datetime = dateutil.parser.parse(value)
    if value_parsed:
        delta = dt.datetime.now(dt.timezone.utc) - value_parsed.astimezone(
            dt.timezone.utc
        )
        return verbose_timedelta(delta)
    else:
        return ""


def datetime_delta_format_until(value):
    if value:
        delta = value.astimezone(dt.timezone.utc) - dt.datetime.now(dt.timezone.utc)
        return verbose_timedelta(delta)
    else:
        return ""


def tx_hash_link(value: str, net: str):
    value_string = (
        f'<a class="ccd sm-text" href="/{net}/transaction/{value}">{value[:4]}</a>'
    )

    return value_string


def block_hash_link(value: str, net: str):
    value_string = f'<a class="ccd sm-text" href="/{net}/block/{value}">{value[:4]}</a>'

    return value_string


def block_height_link(value: int, net: str):
    value_string = f'<a class="ccd sm-text" href="/{net}/block/{value}">{round_x_decimal_with_comma(value, 0)}</a>'

    return value_string


def micro_ccd_no_decimals(value: str):
    try:
        amount = round(int(value) / 1_000_000)
    except:  # noqa: E722
        amount = 0
    ccd_amount_str = f"{amount:,.6f}"
    splits = ccd_amount_str.split(".")
    return f'<span class="ccd">Ͼ{splits[0]}</span>'


def account_label_on_index(
    account_index: int,
    user: UserV2 = None,
    community_labels=None,
    net=None,
    app=None,
    header=False,
    sankey=False,
):
    """
    If it finds a match, it will, depending on whether we are requesting a header pill,
    or a regular account name, display the tag.
    Note that a user label always takes precedence.
    """

    account_label = None
    account_labeled = False
    if isinstance(user, dict):
        user = UserV2(**user)
    if user:
        if user.accounts:
            account_index_to_label = {
                x["account_index"]: x["label"] for x in user.accounts.values()
            }
            user_label = account_index_to_label.get(account_index, None)

            if user_label:
                account_label = (
                    f'<i style="color:#7939BA;" class="bi bi-person-bounding-box pe-1"></i>{user_label}'
                    if not header
                    else f'<span style="margin-top: 12px;" class="badge rounded-pill bg-warning  ms-5 mt-1"><small>{user_label}</small></span>'
                )
                if sankey:
                    account_label = user_label
                account_labeled = True

    if not account_label:
        if community_labels:
            account_labeled = str(account_index) in community_labels["labels_melt"]
            # get_address_identifiers(str(account_index), net)
            if account_labeled:

                account_label = f'<i class="bi bi-person-bounding-box pe-1"></i>{community_labels["labels_melt"][str(account_index)]["label"]}'
                account_labeled = True
        else:
            account_labeled = False
            account_label = None

    return account_labeled, account_label


def hex_to_rgba(hex: str, opacity: float):
    h = hex.lstrip("#")
    rgb = tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
    rgba = rgb + (opacity,)
    return rgba


async def get_address_identifiers(account_address_or_index: str | int, net: str, app):
    """Tranlate account_address to index. Note that this endpoint looks for canonical addresses."""
    if isinstance(account_address_or_index, str):
        account_address = account_address_or_index
        canonical = account_address[:29]
        account_index = None
        if canonical not in app.addresses_to_indexes[net]:
            api_response: APIResponseResult = await post_url_from_api(
                f"{app.api_url}/v2/{net}/accounts/get-indexes",
                app.httpx_client,
                json_post_content=[canonical],
            )
            if api_response.ok:
                app.addresses_to_indexes[net].update(
                    {canonical: api_response.return_value[canonical]}
                )

                account_index = (
                    api_response.return_value[canonical] if api_response.ok else None
                )
                return account_address, canonical, account_index
            else:
                return account_address, canonical, account_index
        else:
            account_index = app.addresses_to_indexes[net][canonical]
            return account_address, canonical, account_index

    else:
        account_address = None
        canonical = None
        account_index = account_address_or_index

        if account_index not in app.indexes_to_addresses[net]:
            api_response: APIResponseResult = await post_url_from_api(
                f"{app.api_url}/v2/{net}/accounts/get-addresses",
                app.httpx_client,
                json_post_content=[account_index],
            )
            if api_response.ok:
                app.indexes_to_addresses[net].update(
                    {account_index: api_response.return_value[account_index]}
                )

                account_address = (
                    api_response.return_value[canonical]
                    if api_response.ok
                    else account_address
                )
                canonical = account_address[:29]
                return account_address, canonical, account_index

        else:
            account_address = app.addresses_to_indexes[net][canonical]
            canonical = account_address[:29]
            return account_address, canonical, account_index


def from_address_to_index(account_address: str, net: str, app):
    """Translate account_address to index. ."""
    try:
        int_value = int(account_address)
        return int_value
    except:  # noqa: E722

        canonical = account_address[:29]
        if canonical not in app.addresses_to_indexes[net]:
            return account_address
        else:
            account_index = app.addresses_to_indexes[net][canonical]
            return int(account_index)


def account_link(
    value: str | int,
    net: str,
    user=None,
    tags=None,
    app=None,
):

    tag_found = False
    if isinstance(user, dict):
        user = UserV2(**user)

    if isinstance(value, str):
        if "<" in value:
            contract = CCD_ContractAddress.from_str(value)
            return f'<a class="" href="/{net}/instance/{contract.index}/{contract.subindex}"><i class="bi bi-card-checklist pe-1"></i>{value}</a>'
        # value is now an index if found, otherwise still an address
        value = from_address_to_index(value, net, app)

    if net == "testnet":
        if isinstance(value, str):
            tag_label = f'<i class="bi bi-person-bounding-box pe-1"></i>{value[:4]}'
        else:
            tag_label = f'<i class="bi bi-person-bounding-box pe-1"></i>{value}'

        return f'<a class="" href="/{net}/account/{value}">{tag_label}</a>'

    if isinstance(value, int):
        tag_found, tag_label = account_label_on_index(value, user, tags, net, app)
    if not tag_found:
        if isinstance(value, str):
            tag_label = f'<i class="bi bi-person-bounding-box pe-1"></i>{value[:4]}'
        else:
            tag_label = f'<i class="bi bi-person-bounding-box pe-1"></i>{value}'

    return f'<a class="" href="/{net}/account/{value}">{tag_label}</a>'


def round_x_decimal_with_comma(value, dec: int):
    if value:
        return f"{value:,.{dec}f}"
    else:
        return value


def round_x_decimal_no_comma(value, dec: int):
    if value:
        return f"{value:.{dec}f}"
    else:
        return value


def lottery_power(value):
    return f"{100*value:,.3f}"


def verbose_timedelta(delta, days_only=False):
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    dstr = "%s day%s" % (delta.days, "s"[delta.days == 1 :])
    hstr = "%s hr%s" % (hours, ""[hours == 1 :])
    mstr = "%s min%s" % (minutes, ""[minutes == 1 :])
    sstr = "%s sec%s" % (seconds, ""[seconds == 1 :])
    total_minutes = delta.days * 24 * 60 + hours * 60 + minutes

    if total_minutes < 2:
        dhms = [dstr, hstr, mstr, sstr] if total_minutes < 2 else [dstr, hstr, mstr]
    elif total_minutes < 120:
        dhms = [dstr, hstr, mstr] if total_minutes < 120 else [dstr, hstr]
    else:
        dhms = [dstr, hstr] if total_minutes < 1440 else [dstr]

    dhms = [dstr] if days_only else dhms

    for x in range(len(dhms)):
        if not dhms[x].startswith("0"):
            dhms = dhms[x:]
            break
    dhms.reverse()
    for x in range(len(dhms)):
        if not dhms[x].startswith("0"):
            dhms = dhms[x:]
            break
    dhms.reverse()
    if (seconds < 5) and (total_minutes < 1):
        return "< 5 sec"
    else:
        return " ".join(dhms)


class EventType:
    def __init__(self, event, update, emit, logged_events: list = None):
        self.event = event
        self.update = update
        self.emit = emit
        self.logged_events: list[EventType] = logged_events

    def __repr__(self):
        return f"{self.event}, {self.update}, {self.emit}"


def shorten_address(value, address=None):
    if len(value) < 17:
        return f"<div class='ccd'>{value}</div>"

    else:
        if address:
            return f"{value[:8]}...{value[-8:]}"
        else:
            ss = f'<br/><div class="ccd">{value}</div>'
            return ss


def decode_memo(hex):
    try:
        bs = io.BytesIO(bytes.fromhex(hex))
        value = bs.read(256)
        try:
            memo = bytes.decode(value, "UTF-8")
            return memo
        except UnicodeDecodeError:
            memo = bytes.decode(value[1:], "UTF-8")
            return memo
    except:  # noqa: E722
        return "Decoding failure..."


def parse_account_or_contract(key, value, net, user, tags, app):
    out = ""
    if isinstance(value, dict):
        sec_key = list(value.keys())[0]
        if sec_key == "Account":
            account_id = value[sec_key][0]
            account_ = account_link(
                account_id,
                net,
                user=user,
                tags=tags,
                app=app,
            )
            out = f"{key}: {account_}<br/>"

        elif sec_key == "Contract":
            contract_id = value[sec_key][0]
            contract = CCD_ContractAddress.from_index(
                contract_id["index"], contract_id["subindex"]
            )
            contract_ = instance_link_v2(contract, net)
            out = f"{key}: {contract_}<br/>"

        elif list(value.keys()) == ["index", "subindex"]:
            contract = CCD_ContractAddress.from_index(value["index"], value["subindex"])
            contract_ = instance_link_v2(contract, net)
            out = f"{key}: {contract_}<br/>"

        elif sec_key == "metadata_url":
            if "url" in value[sec_key]:
                out = f"{key}: <a href='{value[sec_key]['url']}'>{value[sec_key]['url']}</a><br/>"

        elif "url" in list(value.keys()):
            out = f"{key}: <a href='{value['url']}'>{value['url']}</a><br/>"
        else:
            out = f"{key}: {value}<br/>"

    if isinstance(value, str):
        if len(value) < 29:
            out = f"{key}: {value}<br/>"
        elif key == "tokens":
            out += f"{key}: <span class='text-break'>{value[:8]}</span><br/>"
        else:
            account_ = account_link(
                value,
                net,
                user=user,
                tags=tags,
                app=app,
            )
            out += f"{key}: {account_}<br/>"

    if out == "":
        out = f"{key}: {value}<br/>"
    return out


def print_schema_dict(schema_dict, net, user, tags, app):
    if not isinstance(schema_dict, dict):
        if isinstance(schema_dict, list):
            schema_dict = schema_dict[0]
    if isinstance(schema_dict, dict):
        out = '<div class=" parameter ps-4 pe-2">'
        for key, value in schema_dict.items():
            if isinstance(value, dict):
                out += parse_account_or_contract(key, value, net, user, tags, app)
            elif isinstance(value, list) and len(value) > 0:
                out += parse_account_or_contract(key, value[0], net, user, tags, app)
            elif key in [
                "owner",
                "from",
                "to",
                "winner",
                "account",
                "signer",
                "witness",
            ]:
                out += parse_account_or_contract(key, value, net, user, tags, app)
            elif key == "amount":
                if value != "":
                    out += f"{key}: <span class='ccd'>{value}</span><br/>"
            elif key == "data":
                if value != "":
                    out += f"{key}: {shorten_address(value)}"
            elif key == "url":
                if value != "":
                    out += f"{key}: <a href='{value}'>{value}</a>"
            elif key == "tokens":
                if value != "":
                    out += f"{key}: <a href='/{net}/token'>{value}</a>"
            else:
                if value != "":
                    out += f"{key}: {value}<br/>"

        out += "</div>"
    else:
        out = schema_dict
    return out


def datetime_format_day_only_from_ms_timestamp(value):
    ddt = dt.datetime.fromtimestamp(value / 1000)
    return f"{ddt:%Y-%m-%d}"


def token_amount_using_decimals(value: int, decimals: int = None):
    if not decimals:
        return f"{value}"

    return f"{(int(value) * (math.pow(10, -decimals))):,.6f}"


def token_amount_using_decimals_rounded(
    value: int, decimals: int = None, rounded_decimals: int = None
):
    if not decimals:
        return f"{int(value):,.0f}"
    if not rounded_decimals:
        rounded_decimals = 0
    return f"{(int(value) * (math.pow(10, -decimals))):,.{rounded_decimals}f}"


async def process_event_for_makeup(req: ProcessEventRequest):
    cis = CIS()
    if isinstance(req.user, dict):
        req.user = UserV2(**req.user)

    if req.token_information:
        token_tag = req.token_information.id
        single_use_contract = req.token_information.single_use_contract
        decimals = req.token_information.decimals
    else:
        token_tag = None
        single_use_contract = None
        decimals = None

    tag_, result = cis.process_log_events(req.event)
    if result:
        if tag_ in [255, 254, 253, 252, 251, 250]:
            event_type = LoggedEvents(tag_).name
            if "token_id" in result.__dict__:
                token_address = f"<{req.contract_address.index},{req.contract_address.subindex}>-{result.token_id}"

                tagified_token_address = tagified_token_address = (
                    f"<a href='/{req.net}/tokens/_/{token_address}'>{token_address}</a>"
                )

                # special case to show the Web23 domain name

                tagified_token_address = tagified_token_address = (
                    f"<a  class='ccd' href='/{req.net}/tokens/_/{token_address}'>{result.token_id}</a>"
                )

                # token_request = req.db_to_use[
                #     Collections.tokens_token_addresses_v2
                # ].find_one({"_id": token_address})

                try:
                    response: httpx.Response = await req.httpx_client.get(
                        f"{req.app.api_url}/v2/{req.net}/token/{req.contract_address.index}/{req.contract_address.subindex}{result.token_id}/info"
                    )
                    response.raise_for_status()
                    token_address_as_class = MongoTypeTokenAddress(**response.json())
                except httpx.HTTPError:
                    token_address_as_class = None

                display_name = ""
                if token_address_as_class:
                    if token_address_as_class.token_metadata:
                        if token_address_as_class.token_metadata.name:
                            display_name = f"Token name: {token_address_as_class.token_metadata.name}<br/>"

                if token_tag:
                    if single_use_contract:
                        tagified_token_address = f"<a class='ccd' href='/{req.net}/tokens/{token_tag}'>{token_tag}</a>"
                    else:
                        token_display = f"{token_tag}-{result.token_id[:8]}"

                        tagified_token_address = f"<a  class='ccd' href='/{req.net}/tokens/{token_tag}/{result.token_id}'>{token_display}</a>"
                        # f"{token_tag}-{result.token_id}"

            if "token_amount" in result.__dict__:
                if not decimals:
                    amount = result.token_amount
                else:
                    amount = token_amount_using_decimals(result.token_amount, decimals)

                postfix = "s"
                if amount == 1:
                    postfix = ""

                token_string = f"token{postfix}" if not token_tag else f"{token_tag}"
                if token_tag:
                    if single_use_contract:
                        token_string = f"{token_tag}"
                    else:
                        token_string = ""

            if tag_ in [252]:
                owner = address_link(result.owner, req.net, req.user, req.tags, req.app)
                operator = address_link(
                    result.operator, req.net, req.user, req.tags, req.app
                )

            if tag_ in [255, 253]:
                from_address = address_link(
                    result.from_address, req.net, req.user, req.tags, req.app
                )

            if tag_ in [255, 254]:
                to_address = address_link(
                    result.to_address, req.net, req.user, req.tags, req.app
                )

            if tag_ == 250:
                sponsoree = address_link(
                    result.sponsoree, req.net, req.user, req.tags, req.app
                )

            if tag_ == 255:
                return EventType(
                    f"{event_type}",
                    req.app.templates.get_template(
                        f"tx/logged_events/{tag_}.html"
                    ).render(
                        {
                            "tagified_token_address": tagified_token_address,
                            "display_name": display_name,
                            "amount": amount,
                            "token_string": token_string,
                            "from_address": from_address,
                            "to_address": to_address,
                        }
                    ),
                    None,
                )
            if tag_ == 254:
                return EventType(
                    f"{event_type}",
                    req.app.templates.get_template(
                        f"tx/logged_events/{tag_}.html"
                    ).render(
                        {
                            "tagified_token_address": tagified_token_address,
                            "display_name": display_name,
                            "amount": amount,
                            "token_string": token_string,
                            "to_address": to_address,
                        }
                    ),
                    None,
                )

            if tag_ == 253:
                return EventType(
                    f"{event_type}",
                    req.app.templates.get_template(
                        f"tx/logged_events/{tag_}.html"
                    ).render(
                        {
                            "tagified_token_address": tagified_token_address,
                            "display_name": display_name,
                            "amount": amount,
                            "token_string": token_string,
                            "from_address": from_address,
                        }
                    ),
                    None,
                )

            if tag_ == 252:
                return EventType(
                    f"{event_type}",
                    req.app.templates.get_template(
                        f"tx/logged_events/{tag_}.html"
                    ).render(
                        {
                            "result": result,
                            "owner": owner,
                            "operator": operator,
                        }
                    ),
                    None,
                )
            if tag_ == 251:
                return EventType(
                    f"{event_type}",
                    req.app.templates.get_template(
                        f"tx/logged_events/{tag_}.html"
                    ).render(
                        {
                            "tagified_token_address": tagified_token_address,
                            "display_name": display_name,
                            "result": result,
                        }
                    ),
                    None,
                )

            if tag_ == 250:
                return EventType(
                    f"{event_type}",
                    req.app.templates.get_template(
                        f"tx/logged_events/{tag_}.html"
                    ).render(
                        {
                            "sponsoree": sponsoree,
                            "result": result,
                        }
                    ),
                    None,
                )

        elif tag_ in [249, 248, 247, 246, 245, 244]:
            event_type = LoggedEvents(tag_).name
            if tag_ == 249:
                return EventType(
                    f"{event_type}",
                    req.app.templates.get_template(
                        f"tx/logged_events/{tag_}.html"
                    ).render({"result": result}),
                    None,
                )
            if tag_ == 248:
                return EventType(
                    f"{event_type}",
                    req.app.templates.get_template(
                        f"tx/logged_events/{tag_}.html"
                    ).render({"result": result}),
                    None,
                )
            if tag_ == 247:
                return EventType(
                    f"{event_type}",
                    req.app.templates.get_template(
                        f"tx/logged_events/{tag_}.html"
                    ).render({"result": result}),
                    None,
                )
            if tag_ == 246:
                return EventType(
                    f"{event_type}",
                    req.app.templates.get_template(
                        f"tx/logged_events/{tag_}.html"
                    ).render({"result": result}),
                    None,
                )
            if tag_ == 245:
                return EventType(
                    f"{event_type}",
                    req.app.templates.get_template(
                        f"tx/logged_events/{tag_}.html"
                    ).render({"result": result}),
                    None,
                )
            if tag_ == 244:
                return EventType(
                    f"{event_type}",
                    req.app.templates.get_template(
                        f"tx/logged_events/{tag_}.html"
                    ).render({"result": result}),
                    None,
                )
        else:
            return None
    else:
        return None


def address_link(value, net, user, tags, app):
    if isinstance(user, dict):
        user = UserV2(**user)
    return (
        account_link(value, net, user=user, tags=tags, app=app)
        if len(value) == 50
        else instance_link_v2(CCD_ContractAddress.from_str(value), user, tags, net)
    )


class PaginationRequest(BaseModel):
    total_txs: int
    requested_page: int
    word: str
    action_string: str
    limit: Optional[int] = 20
    returned_rows: Optional[int] = None


class PaginationResponse(BaseModel):
    total_txs: int
    requested_page: int
    num_of_pages: int
    start_: bool
    prev_: bool
    next_: bool
    prev_page_request: int
    next_page_request: int
    end_: bool
    from_: int
    to_: int
    word_: str
    action_string_: str
    no_totals: Optional[bool] = False
    returned_rows: Optional[int] = None


def pagination_calculator(req: PaginationRequest) -> PaginationResponse:
    if req.returned_rows:
        # only filled if we do not show totals
        start_ = True
        prev_ = True
        next_ = True
        end_ = False
        action_string = req.action_string
        word_ = (
            req.word.replace("-", " ")
            if req.returned_rows == 1
            else f'{req.word.replace("-"," ")}s'
        )

        from_ = req.requested_page * int(req.limit) + 1
        to_ = (req.requested_page + 1) * int(req.limit)

        response = PaginationResponse(
            total_txs=req.total_txs,
            requested_page=req.requested_page,
            num_of_pages=0,
            start_=start_,
            prev_=prev_,
            next_=next_,
            prev_page_request=req.requested_page - 1,
            next_page_request=req.requested_page + 1,
            end_=end_,
            from_=from_,
            to_=to_,
            word_=word_,
            action_string_=action_string,
            no_totals=True,
            returned_rows=req.returned_rows,
        )
        return response

    else:
        num_of_pages = int(math.ceil(req.total_txs / req.limit))

        # requested page = 0 indicated the first page
        # requested page = -1 indicates the last page

        if req.requested_page == -1:
            req.requested_page = num_of_pages - 1

        if req.requested_page > 0:
            prev_ = True
        elif req.requested_page == -1:
            prev_ = True
        else:
            prev_ = False
        if req.requested_page == -1:
            next_ = False
        elif req.requested_page < (num_of_pages - 1):
            next_ = True
        else:
            next_ = False

        start_ = False if req.requested_page == 0 else True
        end_ = False if (req.requested_page == num_of_pages - 1) else True
        action_string = req.action_string
        word_ = (
            req.word.replace("-", " ")
            if req.total_txs == 1
            else f'{req.word.replace("-"," ")}s'
        )

        from_ = req.requested_page * int(req.limit) + 1
        to_ = min(req.total_txs, (req.requested_page + 1) * int(req.limit))

        response = PaginationResponse(
            total_txs=req.total_txs,
            requested_page=req.requested_page,
            num_of_pages=num_of_pages,
            start_=start_,
            prev_=prev_,
            next_=next_,
            prev_page_request=req.requested_page - 1,
            next_page_request=req.requested_page + 1,
            end_=end_,
            from_=from_,
            to_=to_,
            word_=word_,
            action_string_=action_string,
        )
        return response


def calculate_skip(requested_page, total_rows, limit):
    if requested_page > -1:
        skip = requested_page * limit
    else:
        nr_of_pages, _ = divmod(total_rows, limit)
        skip = nr_of_pages * limit
        # special case if total_rows equals a limit multiple
        if skip == total_rows:
            skip = (nr_of_pages - 1) * limit
    return skip


class APIResponseResult(BaseModel):
    return_value: Optional[Any] = None
    status_code: int
    ok: bool
    message: Optional[str] = None
    duration_in_sec: float

    def get_value_if_ok_or_none(self):
        return


async def get_url_from_api(url: str, httpx_client: httpx.AsyncClient):
    api_response = APIResponseResult(status_code=-1, duration_in_sec=-1, ok=False)
    response = None
    now = dt.datetime.now().astimezone(dt.UTC)
    try:
        response = await httpx_client.get(url)
        try:
            api_response.return_value = response.json()
        except:  # noqa: E722
            # if the response happens to be empty, json decoder gives an error.
            api_response.return_value = None
        api_response.status_code = response.status_code
        api_response.ok = True if response.status_code == 200 else False
    except httpx.HTTPError:
        api_response.return_value = None
        if response:
            api_response.status_code = response.status_code
            api_response.return_value = response.json()

    end = dt.datetime.now().astimezone(dt.UTC)

    api_response.duration_in_sec = (end - now).total_seconds()
    print(f"GET: {api_response.duration_in_sec:2,.4f}s for {url}")
    return api_response


async def post_url_from_api(
    url: str, httpx_client: httpx.AsyncClient, json_post_content: list
):
    api_response = APIResponseResult(status_code=-1, duration_in_sec=-1, ok=False)
    response = None
    now = dt.datetime.now().astimezone(dt.UTC)
    try:
        response = await httpx_client.post(url, json=json_post_content)
        try:
            api_response.return_value = response.json()
        except:  # noqa: E722
            # if the response happens to be empty, json decoder gives an error.
            api_response.return_value = None
        api_response.status_code = response.status_code
        api_response.ok = True if response.status_code == 200 else False
    except httpx.HTTPError:
        api_response.return_value = None
        if response:
            api_response.status_code = response.status_code
            api_response.return_value = response.json()

    end = dt.datetime.now().astimezone(dt.UTC)

    api_response.duration_in_sec = (end - now).total_seconds()
    print(f"POST: {api_response.duration_in_sec:2,.4f}s for {url}")
    return api_response


async def put_url_from_api(
    url: str, httpx_client: httpx.AsyncClient, json_put_content: list
):
    api_response = APIResponseResult(status_code=-1, duration_in_sec=-1, ok=False)
    response = None
    now = dt.datetime.now().astimezone(dt.UTC)
    try:
        response = await httpx_client.put(url, json=json_put_content)
        try:
            api_response.return_value = response.json()
        except:  # noqa: E722
            # if the response happens to be empty, json decoder gives an error.
            api_response.return_value = None
        api_response.status_code = response.status_code
        api_response.ok = True if response.status_code == 200 else False
    except httpx.HTTPError:
        api_response.return_value = None
        if response:
            api_response.status_code = response.status_code
            api_response.return_value = response.json()

    end = dt.datetime.now().astimezone(dt.UTC)

    api_response.duration_in_sec = (end - now).total_seconds()
    print(f"PUT: {api_response.duration_in_sec:2,.4f}s for {url}")
    return api_response


def format_preference_key(value: str):
    value = value.replace("_", " ")
    return value.capitalize()


def user_string(user: UserV2):
    if isinstance(user, dict):
        user = UserV2(**user)
    return user.username if user else "A user"


async def get_theme_from_request(request: Request):
    theme = "dark"
    body = await request.body()
    if body:
        theme = body.decode("utf-8").split("=")[1]
    return theme


@lru_cache
async def get_schema_from_source_utils(app, net: str, contract_address_str: str):
    contract_address = CCD_ContractAddress.from_str(contract_address_str)
    api_result = await get_url_from_api(
        f"{app.api_url}/v2/{net}/contract/{contract_address.index}/{contract_address.subindex}/schema-from-source",
        app.httpx_client,
    )
    api_repsonse = api_result.return_value if api_result.ok else None
    if not api_repsonse:
        schema = None
        source_module_name = None
        return schema, source_module_name

    ms_bytes = base64.decodebytes(json.loads(api_repsonse["module_source"]).encode())

    schema = (
        Schema(ms_bytes, 1) if api_repsonse["version"] == "v1" else Schema(ms_bytes, 0)
    )
    source_module_name = api_repsonse["source_module_name"]
    return schema, source_module_name


def split_into_url_slug(token_address: str):
    contract = CCD_ContractAddress.from_str(token_address.split("-")[0])
    token_id = token_address.split("-")[1]
    return f"{contract.index}/{contract.subindex}/{token_id}"


def split_contract_into_url_slug_and_token_id(contract_str: str, token_id: str):
    contract = CCD_ContractAddress.from_str(contract_str)
    return f"{contract.index}/{contract.subindex}/{token_id}"


def add_account_info_to_cache(account_info: CCD_AccountInfo, app: FastAPI, net: str):
    app.addresses_to_indexes[net][account_info.address[:29]] = account_info.index


def apy_perc(value):
    if value:
        return f"{value*100:.2f}%"
    else:
        return "--"
