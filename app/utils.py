import datetime as dt
import io
import math
import typing

# from app.Recurring.recurring import Recurring
from datetime import timedelta, timezone
from enum import Enum
from typing import Optional
from uuid import UUID

import dateutil.parser
import pytz
import requests
from ccdexplorer_fundamentals.cis import (
    CIS,
    LoggedEvents,
    MongoTypeTokenAddress,
    MongoTypeTokensTag,
    TokenMetaData,
)
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import CCD_ContractAddress
from ccdexplorer_fundamentals.mongodb import Collections, CollectionsUtilities, MongoDB

# This modules should NEVER import from app., or app.classes.
# from ccdexplorer_fundamentals.user import SubscriptionDetails
# from app.Recurring.recurring import Recurring
from ccdexplorer_fundamentals.user_v2 import UserV2
from fastapi import Request
from pydantic import BaseModel
from pymongo.collection import Collection
from rich.console import Console

console = Console()


class ProcessEventRequest(BaseModel):
    class Config:
        arbitrary_types_allowed = True

    contract_address: CCD_ContractAddress
    token_metadata: Optional[TokenMetaData] = None
    event: str
    net: str
    user: Optional[UserV2] = None
    tags: Optional[dict] = None
    db_to_use: dict[Collections, Collection]
    contracts_with_tag_info: dict[str, MongoTypeTokensTag]
    token_addresses_with_markup: Optional[dict] = None
    app: typing.Any = None


class AddressType(Enum):
    AccountAddress = 1
    ContractAddress = 2


class AccountOrContract:
    def __init__(self, value):
        if "<" in value:
            self.address_type = AddressType.ContractAddress
            self.index = value
        else:
            self.address_type = AddressType.AccountAddress

    def as_link(self):
        return f"{self.value}"


class EventType:
    def __init__(self, event, update, emit, logged_events: list = None):
        self.event = event
        self.update = update
        self.emit = emit
        self.logged_events: list[EventType] = logged_events

    def __repr__(self):
        return f"{self.event}, {self.update}, {self.emit}"


def generate_dates_from_start_until_end(start: str, end: str):
    start_date = dateutil.parser.parse(start)
    end_date = dateutil.parser.parse(end)
    date_range = []

    current_date = start_date
    while current_date <= end_date:
        date_range.append(current_date.strftime("%Y-%m-%d"))
        current_date += timedelta(days=1)

    return date_range


def format_preference_key(value: str):
    value = value.replace("_", " ")
    return value.capitalize()


def getattr(object, key):
    return getattr(object, key)


def micro_ccd_display(value: str):
    try:
        amount = int(value) / 1_000_000
    except:
        amount = 0
    ccd_amount_str = f"{amount:,.6f}"
    splits = ccd_amount_str.split(".")
    return f'<span class="ccd">Ͼ{splits[0]}</span>.<span class="ccd_decimals">{splits[1]}</span>'


def micro_ccd_no_decimals(value: str):
    try:
        amount = round(int(value) / 1_000_000)
    except:
        amount = 0
    ccd_amount_str = f"{amount:,.6f}"
    splits = ccd_amount_str.split(".")
    return f'<span class="ccd">Ͼ{splits[0]}</span>'


def token_value_no_decimals(value: str, token: str):
    try:
        amount = int(value)
    except:
        amount = 0
    return f'<span class="ccd">{amount:,.0f} {token}</span>'


def is_valid_uuid4(uuid_: str) -> bool:
    """
    Check whether a string is a valid v4 uuid.
    """
    try:
        return bool(UUID(uuid_, version=4))
    except ValueError:
        return False


def cns_domains_registered(account_id):
    try:
        r = requests.get(
            f"https://cns-api.ccd.domains/api/v1/external/domains?wallet_address={account_id}&page=1&size=2000",
            verify=False,
            timeout=1,
        )
        if r.status_code == 200:
            cns_domains_list = r.json()
            if "data" in cns_domains_list:
                if "data" in cns_domains_list["data"]:
                    if len(cns_domains_list["data"]["data"]) == 0:
                        cns_domains_list = None
        else:
            cns_domains_list = None
    except:
        cns_domains_list = None

    return cns_domains_list


def memory_profiler():
    from pympler import muppy, summary

    mem_summary = summary.summarize(muppy.get_objects())
    rows = summary.format_(mem_summary)
    timestamp = dt.datetime.utcnow()
    rows = "\n".join(rows).split("\n")
    rows = [
        {"type": x.split("|")[0], "object": x.split("|")[1], "size": x.split("|")[2]}
        for x in rows
    ]
    return rows, timestamp


def user_string(user: UserV2):
    if isinstance(user, dict):
        user = UserV2(**user)
    return user.username if user else "A user"


def contract_tag(value, user: UserV2 = None, tags=None, header=False):
    """ """

    tag_label = None
    tag_found = False

    if not tag_label:
        if tags:
            tag_found = False
            # for label_group in tags["labels"].keys():
            label_group = "contracts"
            label_group_color = tags["colors"][label_group]
            for _id, tag in tags["labels"][label_group].items():
                if convert_contract_str_to_type(_id) == value:
                    tag_label = (
                        f"{tag}"
                        if not header
                        else f'<span style="background-color: {label_group_color}" class="badge rounded-pill ms-5 mt-1"><small>{tag}</small></span>'
                    )
                    tag_found = True
        else:
            tag_found = False
            tag_label = None

    return tag_found, tag_label


def account_tag(value, user: UserV2 = None, tags=None, header=False, sankey=False):
    """
    This method looks up an address in account-tags.json, in the concordium-users repo.
    If it finds a match, it will, depending on whether we are requesting a header pill,
    or a regular account name, display the tag.
    Note that a user label always takes precedence.
    """

    tag_label = None
    tag_found = False
    if isinstance(user, dict):
        user = UserV2(**user)
    if user:
        if user.accounts:
            account_id_to_label = {
                x["account_id"]: x["label"] for x in user.accounts.values()
            }
            user_label = account_id_to_label.get(value, None)
            if not user_label:
                canonicals = {x[:29]: x for x in account_id_to_label.keys()}
                if canonicals.get(value, None):
                    user_label = account_id_to_label.get(canonicals.get(value), None)
            if user_label:
                tag_label = (
                    f"👤{user_label}"
                    if not header
                    else f'<span style="margin-top: 12px;" class="badge rounded-pill bg-warning  ms-5 mt-1"><small>{user_label}</small></span>'
                )
                if sankey:
                    tag_label = user_label
                tag_found = True

    if not tag_label:
        if tags:
            tag_found = False
            for label_group in tags["labels"].keys():
                label_group_color = tags["colors"][label_group]
                for address, tag in tags["labels"][label_group].items():
                    if address[:29] == value[:29]:
                        tag_label = (
                            f"🏢{tag}"
                            if not header
                            else f'<span style="background-color: {label_group_color};margin-top: 12px;" class="badge rounded-pill ms-5 "><small>{tag}</small></span>'
                        )
                        if sankey:
                            tag_label = tag
                        tag_found = True
        else:
            tag_found = False
            tag_label = None

    return tag_found, tag_label


#### CIS


def get_token_addresses_with_markup_for_addresses(
    addresses: list, req: Request, db_to_use
):
    contracts_with_tag_info = req.app.contracts_with_tag_info
    # get exchange rates
    coll = req.app.mongodb.utilities[CollectionsUtilities.exchange_rates]
    exchange_rates = {x["token"]: x for x in coll.find({})}

    # now onto the token_addresses
    token_addresses_with_markup = {
        x["_id"]: MongoTypeTokenAddress(**x)
        for x in db_to_use[Collections.tokens_token_addresses_v2].find(
            {"_id": {"$in": addresses}}
        )
    }

    for address in token_addresses_with_markup.keys():
        token_address_class = token_addresses_with_markup[address]
        if token_address_class.contract in contracts_with_tag_info.keys():
            token_address_class.tag_information = contracts_with_tag_info[
                token_address_class.contract
            ]
            if token_address_class.tag_information.token_type == "fungible":
                if (
                    token_address_class.tag_information.get_price_from
                    in exchange_rates.keys()
                ):
                    token_address_class.exchange_rate = exchange_rates[
                        token_address_class.tag_information.get_price_from
                    ]["rate"]
                else:
                    token_address_class.exchange_rate = 0
        else:
            token_address_class.tag_information = None
        token_addresses_with_markup[address] = token_address_class

    return token_addresses_with_markup


def address_link(value, net, user, tags, app):
    if isinstance(user, dict):
        user = UserV2(**user)
    return (
        account_link(
            value, net, from_=False, nothing_=True, user=user, tags=tags, app=app
        )
        if len(value) == 50
        else instance_link_v2(convert_contract_str_to_type(value), user, tags, net)
    )


def retrieve_metadata_for_stored_token_address(
    token_address: str, db_to_use: dict[Collections, Collection]
) -> TokenMetaData:
    stored_token_address = db_to_use[Collections.tokens_token_addresses_v2].find_one(
        {"_id": token_address}
    )
    metadata = None
    if stored_token_address:
        stored_token_address = MongoTypeTokenAddress(**stored_token_address)
        url = stored_token_address.metadata_url
        if url:
            try:
                r = requests.get(url, timeout=1)
                if r.status_code == 200:
                    try:
                        metadata = TokenMetaData(**r.json())
                    except Exception as e:
                        metadata = None
                        console.log(
                            f"{e}: Could not convert {r.json()} to TokenMetaData..."
                        )
            except Exception as e:
                metadata = None
                console.log(f"{e}: Request Error...")
    return metadata


def token_tag_if_exists(contract_address: CCD_ContractAddress, db_to_use):
    token_tags = db_to_use[Collections.tokens_tags].find({})
    tag_found = False
    for token_tag in token_tags:
        if contract_address.to_str() in token_tag["contracts"]:
            tag_found = True
            break

    if not tag_found:
        return None
    else:
        return MongoTypeTokensTag(
            **token_tag
        )  # ["_id"], token_tag["single_use_contract"]


# provenance tags, large transaction: 23ed36434d62c8d31eb21e5b1055dd013f0411c7dd5ca3b7ed2e72dd4ae3e3c3


def process_event_for_makeup(req: ProcessEventRequest):
    cis = CIS()
    if isinstance(req.user, dict):
        req.user = UserV2(**req.user)
    contract_address_as_str = req.contract_address.to_str()
    if contract_address_as_str in req.contracts_with_tag_info:
        token_tag = req.contracts_with_tag_info[contract_address_as_str].token_tag_id
        single_use_contract = req.contracts_with_tag_info[
            contract_address_as_str
        ].single_use_contract
        decimals = req.contracts_with_tag_info[contract_address_as_str].decimals
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

                token_request = req.db_to_use[
                    Collections.tokens_token_addresses_v2
                ].find_one({"_id": token_address})
                if token_request:
                    token_address_as_class = MongoTypeTokenAddress(**token_request)
                else:
                    print(token_address)
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
                    f"Token address: {tagified_token_address}<br>{display_name}Transfer amount: {amount} {token_string}<br>From: {from_address}<br>To: {to_address}",
                    None,
                )
            if tag_ == 254:
                return EventType(
                    f"{event_type}",
                    f"Token address: {tagified_token_address}<br>{display_name}Mint amount: {amount} {token_string}<br>To: {to_address}",
                    None,
                )

            if tag_ == 253:
                return EventType(
                    f"{event_type}",
                    f"Token address: {tagified_token_address}<br>{display_name}Burn amount: {amount} {token_string}<br>From: {from_address}",
                    None,
                )

            if tag_ == 252:
                return EventType(
                    f"{event_type}",
                    f"Action: {result.operator_update}<br>Owner: {owner}<br>Operator: {operator}",
                    None,
                )
            if tag_ == 251:
                return EventType(
                    f"{event_type}",
                    f"Token address: {tagified_token_address}<br>{display_name}Metadata Url: <a href='{result.metadata.url}'>{result.metadata.url[8:15]}...{result.metadata.url[-6:]}</a>",
                    None,
                )

            if tag_ == 250:
                return EventType(
                    f"{event_type}",
                    f"Nonce: {result.nonce}<br>Sponsoree: {sponsoree}</a>",
                    None,
                )

        elif tag_ in [249, 248, 247, 246, 245, 244]:
            event_type = LoggedEvents(tag_).name
            if tag_ == 249:
                return EventType(
                    f"{event_type}",
                    f"Credential ID: {result.credential_id}<br>Schema Ref: <a href='{result.schema_ref.url}'>{shorten_address(result.schema_ref.url, address=True)}</a><br/></a>",
                    None,
                )
            if tag_ == 248:
                return EventType(
                    f"{event_type}",
                    f"Credential ID: {result.credential_id}<br>Revoker: {result.revoker}",
                    None,
                )
            if tag_ == 247:
                return EventType(
                    f"{event_type}",
                    f"Metadata Url: <a href='{result.metadata.url}'>{result.metadata.url[8:15]}...{result.metadata.url[-6:]}</a>",
                    None,
                )
            if tag_ == 246:
                return EventType(
                    f"{event_type}",
                    f"Credential ID: {result.credential_id}<br>Metadata Url: <a href='{result.metadata.url}'>{result.metadata.url[8:15]}...{result.metadata.url[-6:]}</a>",
                    None,
                )
            if tag_ == 245:
                return EventType(
                    f"{event_type}",
                    f"Credential Type: {result.type}<br>Schema Ref: <a href='{result.schema_ref.url}'>{shorten_address(result.schema_ref.url, address=True)}</a><br/></a>",
                    None,
                )
            if tag_ == 244:
                return EventType(
                    f"{event_type}",
                    f"Action: {result.action}",
                    None,
                )
        else:
            return None
    else:
        return None

    #### CIS


def convert_contract_str_to_type(value: str) -> CCD_ContractAddress:
    index = int(value.split(",")[0][1:])
    subindex = int(value.split(",")[1][:-1])
    return CCD_ContractAddress(**{"index": index, "subindex": subindex})


def address_to_index(value, app=None):
    if app:
        if app.nightly_accounts_by_account_id.get(value[:29]):
            value = app.nightly_accounts_by_account_id.get(value[:29])["index"]
    return value


def get_usecases(mongodb: MongoDB):
    usecase_ids = {}
    result = mongodb.utilities[CollectionsUtilities.usecases].find({})
    for usecase in list(result):
        mainnet_usecase_addresses = mongodb.mainnet[Collections.usecases].find(
            {"usecase_id": usecase["usecase_id"]}
        )
        for address in mainnet_usecase_addresses:
            if address["type"] == "account_address":
                usecase_ids[usecase["display_name"]] = usecase["usecase_id"]

    return usecase_ids


def get_projects(mongodb: MongoDB):
    project_ids = {}
    result = mongodb.utilities[CollectionsUtilities.projects].find({})
    for project in list(result):
        mainnet_project_addresses = mongodb.mainnet[Collections.projects].find(
            {"project_id": project["project_id"]}
        )
        for address in mainnet_project_addresses:
            project_ids[project["display_name"]] = project["project_id"]

    return project_ids


def get_all_project_ids(mongodb: MongoDB):
    project_ids = {}
    result = mongodb.utilities[CollectionsUtilities.projects].find({})
    for project in list(result):
        project_ids[project["project_id"]] = project

    return project_ids


def account_link(
    value,
    net: str,
    from_,
    nothing_=False,
    user=None,
    tags=None,
    cns=False,
    white_text=False,
    show_tab=None,
    tab=None,
    subtab=None,
    app=None,
):
    if isinstance(user, dict):
        user = UserV2(**user)
    tag_found, tag_label = account_tag(value, user, tags)
    if not tag_found:
        tag_label = f"👤{value[:4]}"

    from_string = "from: " if from_ else "to: "
    if nothing_:
        from_string = ""

    text_color = " text-white " if white_text else ""
    tab_to_link = f"?show_tab={show_tab}" if show_tab else ""
    tab = f"?tab={tab}" if tab else ""
    subtab = f"&subtab={subtab}" if subtab else ""

    if app:
        if app.nightly_accounts_by_account_id:
            if app.nightly_accounts_by_account_id.get(value[:29]):
                value = app.nightly_accounts_by_account_id.get(value[:29])["index"]
                if not tag_found:
                    tag_label = f"👤{value}"

    if not cns:
        return f'<b>{from_string}</b><a class="small {text_color}" href="/{net}/account/{value}{tab}{subtab}">{tag_label}</a>'
    else:
        # if not canonical:
        return f'<b>{from_string}</b><a class="small cns {text_color}" href="/{net}/account/{value}{tab}{subtab}"><b>{tag_label}</b></a>'
        # else:
        #     return f'<b>{from_string}</b><a class="small cns {text_color}" href="/go/{value}"><b>{tag_label}</b></a>'


def verbose_timedelta_accounts_response(delta, days_only=False):
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    dstr = "%s day%s" % (delta.days, "s"[delta.days == 1 :])
    hstr = "%s hr%s" % (hours, "s"[hours == 1 :])
    mstr = "%s min%s" % (minutes, "s"[minutes == 1 :])
    sstr = "%s sec%s" % (seconds, ""[seconds == 1 :])
    total_minutes = delta.days * 24 * 60 + hours * 60 + minutes
    if total_minutes < 30:
        dhms = [mstr]
    elif total_minutes < 60 * 2:
        dhms = [hstr, mstr]
    elif total_minutes < 60 * 24:
        dhms = [hstr]
    else:
        dhms = [dstr]

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
    return " ".join(dhms)


def ccd_amount(value):
    try:
        amount = int(value) / 1_000_000
    except:
        amount = 0

    return amount


def commafy(value):
    return f"{value:,.6f}"


def cost_html(value, energy):
    if energy:
        return f'<small><b>Energy: </b><span class="ccd">{int(value):,.0f}</span> NRG</small>'
    else:
        return f"<small><b>Cost: </b>{micro_ccd_display(value)}</small>"


def datetime_delta_format_schedule_node(value):
    if value:
        delta = dt.datetime.now() - dt.datetime.fromtimestamp(value / 1000)
        return verbose_timedelta(delta)
    else:
        return ""


def datetime_delta_format_since(value):
    if value:
        delta = dt.datetime.now(dt.timezone.utc) - value.astimezone(dt.timezone.utc)
        return verbose_timedelta(delta)
    else:
        return ""


def verbose_timedelta(delta, days_only=False):
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    dstr = "%s day%s" % (delta.days, "s"[delta.days == 1 :])
    hstr = "%s hr%s" % (hours, "s"[hours == 1 :])
    mstr = "%s min%s" % (minutes, "s"[minutes == 1 :])
    sstr = "%s sec%s" % (seconds, ""[seconds == 1 :])
    total_minutes = delta.days * 24 * 60 + hours * 60 + minutes
    if total_minutes < 30:
        dhms = [dstr, hstr, mstr, sstr] if total_minutes < 30 else [dstr, hstr, mstr]
    elif total_minutes < 720:
        dhms = [dstr, hstr, mstr] if total_minutes < 720 else [dstr, hstr]
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
    return " ".join(dhms)


def dec_smaller(value: str):
    splits = value.split(".")
    return f'<span class="ccd">{splits[0]}</span>.<span class="ccd_decimals">{splits[1]}</span>'


def token_amount_using_decimals(value: int, decimals: int = None):
    if not decimals:
        return f"{value}"

    return f"{(value * (math.pow(10, -decimals))):,.6f}"


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
    return f'<small><a href="/{net}/instance/{value.index}/{value.subindex}">&#128462;{tag_label}</a></small>'


def instance_link_from_str(value: str, net: str, user=None, tags=None):
    if isinstance(user, dict):
        user = UserV2(**user)
    return instance_link_v2(convert_contract_str_to_type(value), user, tags, net)


def instance_link(value):
    # address = value.strip('>').strip('<').split(', ')
    # if len(address) > 1:
    return f'<small><a href="/instance/{value["index"]}/{value["subindex"]}">{value}</a></small>'
    # else:
    #     return value

    # address = value.strip('>').strip('<').split(', ')
    # if len(address) > 1:
    #     return f'<small><a href="/instance/{address[0]}/{address[1]}">{value}</a></small>'
    # else:
    #     return value


def instance_link_separate(index, subindex):
    return f'<small><a href="/instance/{index}/{subindex}"><{index},{subindex}></a></small>'


# def instance_link(value):
#     print (value)
#     return f'<small><b>{value}</b><a href="/account/{value}">{value}</a></small>'


def tx_hash_link(value, net: str, env=None, schedule=False, icon_only=False):
    if not schedule:
        return f'<small><b>tx Hash: </b><a class="small" href="/{net}/transaction/{value}">📒{value[:8]}</a></small>'
    elif not icon_only:
        return f'<small><a class="small" href="/{net}/transaction/{value}">📒{value[:8]}</a></small>'
    else:
        return (
            f'<small><a class="small" href="/{net}/transaction/{value}">📒</a></small>'
        )


def block_height_link(value, net: str, env=None, no_text=False):
    if not no_text:
        value_string = f'<small><b>block: </b><a class="small ccd" href = "/{net}/block/{value}">🝙{value}</a></small>'
    else:
        value_string = f'<a class="small ccd" href = "/{net}/block/{value}">🝙</a>'

    return value_string


def strip_message(value):
    return value.split(", message")[0]


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


def decode_memo(hex):
    # bs = bytes.fromhex(hex)
    # return bytes.decode(bs[1:], 'UTF-8')
    try:
        bs = io.BytesIO(bytes.fromhex(hex))
        value = bs.read(256)
        try:
            memo = bytes.decode(value, "UTF-8")
            return memo
        except UnicodeDecodeError:
            memo = bytes.decode(value[1:], "UTF-8")
            return memo
    except:
        return "Decoding failure..."


# def decode_memo(value):
#     fromhex = bytes.fromhex(value)
#     try:
#         encoding_guess = chardet.detect(fromhex[1:])['encoding']
#     except:
#         encoding_guess = 'UTF-8'
#     # print (fromhex.decode(encoding_guess))

#     try:
#         rr = fromhex[1:].decode(encoding_guess)
#     except:
#         rr = ''
#     return rr


def earliest(earliest_win_time: dt.datetime):
    now = dt.datetime.now().astimezone(tz=timezone.utc)
    if now < earliest_win_time:
        return verbose_timedelta(earliest_win_time - now)
    else:
        return "0 sec"


def datetime_format_regular(value):
    if not isinstance(value, dt.datetime):
        the_date = dateutil.parser.parse(value).astimezone(dt.timezone.utc)
    else:
        the_date = value.astimezone(dt.timezone.utc)

    return f"{the_date:%Y-%m-%d %H:%M:%S}"


def datetime_format_schedule(value):
    if not isinstance(value, dt.datetime):
        schedule_date = dateutil.parser.parse(value).astimezone(dt.timezone.utc)
    else:
        schedule_date = value.astimezone(dt.timezone.utc)
    now = dt.datetime.now().astimezone(dt.timezone.utc)
    # timezone = pytz.UTC
    # now = timezone.localize(now)

    delta = schedule_date - now

    return verbose_timedelta(
        delta, days_only=True
    )  # (dt.datetime.now() - dt.datetime.fromtimestamp(value))


def reporting_number(value: int):
    return f"{value:5,.0f}"


def datetime_format_schedule_node(value):
    # ddt = dt.datetime.fromtimestamp(value/1000)
    ddt = dt.datetime.fromtimestamp(value / 1000)
    return ddt


def datetime_timestamp_reporting(value):
    return f'{dt.datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S"):%Y-%m-%d}'


def datetime_format(value):
    delta = dt.datetime.now() - dt.datetime.fromtimestamp(value)

    return verbose_timedelta(
        delta
    )  # (dt.datetime.now() - dt.datetime.fromtimestamp(value))


def regular_datetime_format(value):
    return f"{value:%Y-%m-%d %H:%M:%S}"


def datetime_format_isoparse(value):
    return f"{dateutil.parser.isoparse(value):%Y-%m-%d %H:%M:%S}"


def datetime_format_isoparse_day_only(value):
    return f"{dateutil.parser.isoparse(value):%Y-%m-%d}"


def datetime_format_day_only(value):
    return f"{value:%Y-%m-%d}"


def lp(value):
    return f"{100*value:,.4f}"


def ccd_per_euro(value):
    return f"{value:,.3f}"


def round_1_decimal_no_comma(value):
    return f"{value:.1f}"


def round_x_decimal_no_comma(value, dec):
    return f"{value:.{dec}f}"


def ql_apy_perc(value):
    if value:
        return f"{value*100:.2f}%"
    else:
        return "--"


def round_0_decimal_with_comma(value):
    try:
        return f"{value:,.0f}"
    except:
        return value


def expectation(value, blocks_baked):
    if round(value, 0) == 1:
        plural = ""
    else:
        plural = "s"
    if value < 5:
        expectation_string = f"{blocks_baked:,.0f} / {value:,.2f} block{plural}"
    else:
        expectation_string = f"{blocks_baked:,.0f} / {value:,.0f} block{plural}"
    return expectation_string


def find_baker_node_info(value, bakers_by_account_id, nodes_by_baker_id):
    baker = bakers_by_account_id.get(value, None)
    if baker:
        baker_id = baker.via_client.accountBakerPoolStatus.bakerId
        baker_str = f'<td class="small"><small><a class="small" href ="/account/{value}">{baker_id}</a></small></td>'
    else:
        baker_id = value[:4]
        baker_str = f'<td class="small"><small><span>{account_link(value, from_=False, nothing_=True)}</span></small></td>'

    node = nodes_by_baker_id.get(baker_id, None)
    if node:
        node_str = f'<td><a class="small" href ="/node/{node.nodeId}"><small>{node.nodeName}</small><a></td>'
    else:
        node_str = (
            '<td><span class="small"><small>No Dashboard Entry</small><span></td>'
        )

    return baker_str + node_str


def sort_finalizers(value):
    return sorted(value, key=lambda row: int(row["amount"]), reverse=True)


def sort_finalizers_v2(value):
    return sorted(value, key=lambda row: int(row.amount), reverse=True)


def sort_account_rewards(value):
    return sorted(value, key=lambda row: int(row["bakerReward"]), reverse=True)


def sort_delegators(value):
    return sorted(value, key=lambda row: int(row["stakedAmount"]), reverse=True)


def apy_perc(value):
    if str(value) == "nan":
        return "-----"
    else:
        return f"{value*100:,.2f}%"


def human_format(num):
    num = float("{:.3g}".format(num))
    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0
    return "{}{}".format(
        "{:f}".format(num).rstrip("0").rstrip("."), ["", "K", "M", "B", "T"][magnitude]
    )


def baker_ccd(value):
    return f"{value:,.0f}"


def prob(value):
    return f"{value:,.2f}%"


def thousands(value):
    return f"{value:,.0f}"


def parse_account_or_contract(key, value, net, user, tags, app):
    out = ""
    if isinstance(value, dict):
        sec_key = list(value.keys())[0]
        if sec_key == "Account":
            account_id = value[sec_key][0]
            account_ = account_link(
                account_id,
                net,
                from_=False,
                nothing_=True,
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
        else:
            account_ = account_link(
                value,
                net,
                from_=False,
                nothing_=True,
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
        out = '<div class="ps-4 pe-2">'
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
            else:
                if value != "":
                    out += f"{key}: {value}<br/>"

        out += "</div>"
    else:
        out = schema_dict
    return out


def shorten_address(value, address=None):
    if len(value) < 17:
        return f"<div class='ccd'>{value}</div>"

    else:
        if address:
            return f"{value[:8]}...{value[-8:]}"
        else:
            n = 36
            chunks = [value[i : i + n] for i in range(0, len(value), n)]

            ss = f'<br/><div class="ccd">{"<br/>".join(chunks)}</div>'
            return ss


def creation_date(value):
    return f"{dateutil.parser.parse(value):%b %Y}"


def block_compare(node, chain):
    if (chain - node) < 5:
        return "Yes"
    else:
        return f"No...{(chain-node):,.0f} blocks behind."


def subscription_end_date(value):
    days_until_end = (value - dt.datetime.now(pytz.utc)).days
    s = "" if days_until_end == 1 else "s"
    return f"{value:%Y-%m-%d} ({days_until_end:,.0f} \nday{s} left)"


def subscription_start_date(value):
    return f"{value:%Y-%m-%d}"


def check_account_for_being_exchange_alias(value, tags):
    exchange_accounts = tags["labels"]["exchanges"]

    for exch, address in exchange_accounts.items():
        if address[:29] == value[:29]:
            return address
    return value


def prepare_title(request):
    last_slash_index = request.rfind("/")
    if (last_slash_index > 0) and (last_slash_index < (len(request) - 1)):
        the_title = request[(last_slash_index + 1) :]
        the_title = the_title.replace("-", " ")

        return f" | {the_title.title()}"
    else:
        return ""


def baker_link_with_label(baker_id, recurring, user=None, tags=None):
    return f'<a class="small" href="/account/{baker_id}">{baker_id}</a>'


def baker_link_with_label_no_chain(baker_id, account_id, user: UserV2 = None):
    if isinstance(user, dict):
        user = UserV2(**user)
    if user:
        if user.labels:
            label = user.labels.get(account_id, baker_id)
        else:
            label = baker_id
    else:
        label = baker_id
    return f'<a class="small" href="/account/{baker_id}">{label}</a>'


def decide(value, user, tags):
    if isinstance(user, dict):
        user = UserV2(**user)
    if isinstance(value, str):
        if value[:7] == "ipfs://":
            return f'<a href="https://img.tofunft.com/ipfs/{value[7:]}">IPFS link (note: slow, possibly down)</a>'
        if len(value) == 50:  # an address
            return account_link(value, False, True, user, tags)

    return value


def expectation_view(expectation):
    if expectation < 5:
        expectation_string = f"{expectation:,.2f}"
    else:
        expectation_string = f"{expectation:,.0f}"

    return expectation_string


def token_amount(value):
    return f"{value:,.0f}"
