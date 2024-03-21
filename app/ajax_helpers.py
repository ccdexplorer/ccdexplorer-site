# from scipy.fft import dct
# from app.__chain import *
# ruff: noqa: F403, F405, E402, E501

import math
from app.env import *
from app.classes.Enums import *
from app.classes.dressingroom import QLPoolStatus, TransactionClassifier

# from ccdexplorer_fundamentals.account import (
#     AccountBakerPoolStatus,
#     ConcordiumAccount,
#     ConcordiumAccountFromClient,
# )

# from app.db import *
from app.jinja2_helpers import *
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

# db = DB()


def row_count_helper(len_rows, limit, current_page):
    if len_rows <= int(limit):
        are = "are" if ((len_rows > 1) or (len_rows == 0)) else "is"
        s = "s" if len_rows > 1 else ""
        html = f'<p class="small">There {are} <span id="row_count">{len_rows}</span> tx{s}.</p>'
    else:
        num_of_pages = int(math.ceil(len_rows / int(limit)))
        start = (
            ""
            if int(current_page) < 2
            else f'<button type="button" onclick="prev({int(current_page)}, 0)" class="btn btn-sm btn-outline-primary" id="pagination"><<</button>'
        )
        prev = (
            ""
            if int(current_page) == 0
            else f'<button type="button" onclick="prev({int(current_page)}, {int(current_page) - 1})" class="btn btn-sm btn-outline-primary" id="pagination"><</button>'
        )
        next = (
            ""
            if int(current_page) == (num_of_pages - 1)
            else f'<button type="button" onclick="next({int(current_page)}, {int(current_page) + 1})"class="btn btn-sm btn-outline-primary" id="pagination">></button>'
        )
        end = (
            ""
            if (int(current_page) >= (num_of_pages - 2))
            else f'<button type="button" onclick="next({int(current_page)}, {num_of_pages - 1})"class="btn btn-sm btn-outline-primary" id="pagination">>></button>'
        )
        count_str = f'<small>Showing {(int(current_page)*int(limit)+1):,.0f} to {(min(len_rows, (int(current_page)+1)*int(limit))):,.0f} from <span title="{len_rows}" id="row_count">{len_rows:,.0f}</span> txs.</small>'

        html = (
            '<div class="clearfix">'
            f'<div style="padding-left: 10px;" class="float-start small pe-4">{count_str}</div>'
            f'<div class="float-end small pe-4">{start}{prev}{next}{end}</div>'
            "</div>"
        )
    return html


def transactions_html_header(
    account_id,
    pageInfo,
    len_rows,
    current_page,
    tx_tabs,
    tx_tabs_active,
    block_transactions=False,
):
    html = ""
    html += ql_nodes_paging_html_header(pageInfo, len_rows, current_page, "tx")
    html += '<ul class="nav nav-tabs ms-1 me-1" id="myTab" role="tablist">'

    for tab in TransactionClassifier:
        if len(tx_tabs[tab]) > 0:
            active_str = "active" if tx_tabs_active[tab] else ""
            html += (
                '<li class="nav-item" role="presentation">'
                f'<button class="nav-link small ps-2 pe-2 {active_str}" id="{tab.value}-tab" data-bs-toggle="tab" data-bs-target="#{tab.value[:3]}" type="button" role="tab" aria-controls="{tab.value[:3]}" aria-selected="true"><small>{tab.value} ({len(tx_tabs[tab])})</small></button>'
                "</li>"
            )

    html += "</ul>\n" '<div class="tab-content" id="myTabContent">\n'

    return html


def mongo_transactions_html_header(
    account_id,
    total_len_rows,
    current_page,
    tx_tabs,
    tx_tabs_active,
    block_transactions=False,
    word="tx",
):
    html = ""
    html += mongo_pagination_html_header(total_len_rows, current_page, word)
    html += '<ul class="nav nav-tabs ms-1 me-1" id="myTab" role="tablist">'

    for tab in TransactionClassifier:
        if len(tx_tabs[tab]) > 0:
            active_str = "active" if tx_tabs_active[tab] else ""
            html += (
                '<li class="nav-item" role="presentation">'
                f'<button class="nav-link small ps-2 pe-2 {active_str}" id="{tab.value}-tab" data-bs-toggle="tab" data-bs-target="#{tab.value[:3]}" type="button" role="tab" aria-controls="{tab.value[:3]}" aria-selected="true"><small>{tab.value} ({len(tx_tabs[tab])})</small></button>'
                "</li>"
            )

    html += "</ul>\n" '<div class="tab-content" id="myTabContent">\n'

    return html


# def delegators_html_header(account_id, pageInfo, len_rows, current_page):

#     html = ql_nodes_paging_html_header(pageInfo, len_rows, current_page)
#     transfer_active_str = 'active' if len_transfer > 0 else ''
#     alias_active_str    = 'active' if ((len_transfer == 0) and (len_alias > 0)) else ''
#     smart_active_str    = 'active' if ((len_transfer == 0) and (len_alias == 0) and (len_smart_contract > 0)) else ''
#     baking_active_str   = 'active' if ((len_transfer == 0) and (len_alias == 0) and (len_smart_contract == 0) and (len_baking > 0)) else ''
#     identity_active_str = 'active' if ((len_transfer == 0) and (len_alias == 0) and (len_smart_contract == 0) and (len_baking == 0) and (len_identity > 0)) else ''

#     html += (
#     '<li class="nav-item" role="presentation">'
#         f'<button class="nav-link small ps-2 pe-2 active" id="delegators-tab" data-bs-toggle="tab" data-bs-target="#delegators" type="button" role="tab" aria-controls="transfer" aria-selected="true"><small>Delegators</small></button>'
#     '</li>'
#     )
#     if len_alias > 0:
#         html += (
#         '<li class="nav-item" role="presentation">'
#             f'<button class="nav-link small ps-2 pe-2 {alias_active_str}" id="alias-tab" data-bs-toggle="tab" data-bs-target="#alias" type="button" role="tab" aria-controls="alias" aria-selected="true"><small>Self ({len_alias})</small></button>'
#         '</li>'
#         )
#     if len_smart_contract > 0:
#         html += (
#         '<li class="nav-item" role="presentation">'
#             f'<button class="nav-link small ps-2 pe-2 {smart_active_str}" id="smart-tab" data-bs-toggle="tab" data-bs-target="#smart" type="button" role="tab" aria-controls="smart" aria-selected="true"><small>Smart cts ({len_smart_contract})</small></button>'
#         '</li>'
#         )
#     if len_baking > 0:
#         html += (
#         '<li class="nav-item" role="presentation">'
#             f'<button class="nav-link small ps-2 pe-2 {baking_active_str}" id="baking-tab" data-bs-toggle="tab" data-bs-target="#baking" type="button" role="tab" aria-controls="baking" aria-selected="true"><small>Baking ({len_baking})</small></button>'
#         '</li>'
#         )
#     if len_identity > 0:
#         html += (
#         '<li class="nav-item" role="presentation">'
#             f'<button class="nav-link small ps-2 pe-2 {identity_active_str}" id="identity-tab" data-bs-toggle="tab" data-bs-target="#identity" type="button" role="tab" aria-controls="identity" aria-selected="true"><small>Identity ({len_identity})</small></button>'
#         '</li>'
#         )

#     html += (
#         '</ul>\n'
#         '<div class="tab-content" id="myTabContent">\n'
#     )

#     return html


def transactions_html_footer():
    html = '<!-- class="tab-content" id="myTabContent" -->\n' "</div>\n"
    return html


def get_sum_amount_from_events(t):
    sum = 0
    if "events" in t["result"].keys():
        for event in t["result"]["events"]:
            if "amount" in event.keys():
                sum += int(event["amount"])
    return sum


def get_baker_rewards_from_events(t):
    sum = 0
    if "bakerRewards" in t.keys():
        for reward in t["bakerRewards"]:
            if "amount" in reward.keys():
                sum += int(reward["amount"])
    return sum


def get_memo_from_events(t):
    memo = ""
    for event in t["result"]["events"]:
        if "memo" in event.keys():
            memo += event["memo"]
    return memo


def get_to_from_events(t, schedule=False):
    to = ""
    for event in t["result"]["events"]:
        if "to" in event.keys():
            if not schedule:
                to += event["to"]["address"]
            else:
                to += event["to"]
    return to


def get_schedule_from_events(t):
    schedule = []
    for event in t["result"]["events"]:
        if (
            event["tag"] == "TransferredWithSchedule"
        ):  # this is the event with the amounts
            for s in event["amount"]:
                schedule.append({"amount": s[1], "timestamp": s[0]})
    return schedule


def get_failure_reason(t):
    for key in t["result"]:
        try:
            if "tag" in t["result"][key].keys():
                return t["result"][key]["tag"]
        except:
            pass
    return ""


def process_transactions_to_HTML(rows, tab_string: str, active: bool, tags):
    active_str = "active" if active else ""

    # header for the specific tab
    html = f'<div class="tab-pane fade show {active_str} " style="padding-top: 10px;" id="{tab_string[:3]}" role="tabpanel" aria-labelledby="{tab_string[:3]}-tab">\n'

    # the transactions
    for row in rows:
        html += templates.get_template("intermediate/transaction.html").render(
            {
                "transaction": row.dct,
                "tags": tags,
                "cns_domain_name": row.cns_domain.domain_name,
                "events_list": row.events_list,
                "cns_tx_message": row.cns_domain.action,
                "classified_tx": row,
            }
        )

    # closing the header
    html += '<!-- class="tab-pane fade -->\n' "</div>\n"

    return html


# NODES


def nodes_html_header(
    nodes,
    key,
    chosen_direction,
    len_nodes,
    len_bakers,
    len_reporting_bakers,
    show_bakers_only,
    last_payday,
):
    html = templates.get_template("nodes/header.html").render(
        {
            "len_nodes": len_nodes,
            "len_bakers": len_bakers,
            "len_reporting_bakers": len_reporting_bakers,
            "last_payday": last_payday,
            "show_bakers": show_bakers_only,
            "key": key,
            "SortKey": SortKey,
            "chosen_direction": chosen_direction,
            "Direction": Direction,
        }
    )

    # for sortKey in SortKey:
    #     if key == sortKey.name:
    #         html += f'<option class="small" value="{sortKey.name}" selected>{sortKey.value}</option>'
    #     else:
    #         html += f'<option class="small" value="{sortKey.name}">{sortKey.value}</option>'

    # html += (
    #     '</select>'
    #     '<select class="form-select-sm" id="direction" onchange="val()">'
    # )
    # for direction in Direction:
    #     if chosen_direction == direction.name:
    #         html += f'<option value="{direction.name}" selected>{direction.value}</option>'
    #     else:
    #         html += f'<option value="{direction.name}">{direction.value}</option>'

    # html += (
    #     '</select></div></div>'
    # )
    return html


def process_nodes_to_HTML(
    items,
    last_payday,
    key,
    chosen_direction,
    len_nodes,
    len_bakers,
    len_reporting_bakers,
    baker_nodes_by_baker_id,
    non_reporting_bakers_by_baker_id,
    non_baker_nodes_by_node_id,
    show_bakers,
    user,
    gitbot_tags,
    net,
):
    html = nodes_html_header(
        items,
        key,
        chosen_direction,
        len_nodes,
        len_bakers,
        len_reporting_bakers,
        show_bakers,
        last_payday,
    )
    for index, item in enumerate(items):
        baker = item["baker"]
        node = item["node"]

        if baker:
            tag_found, tag_label = account_tag(
                baker["pool_status"]["address"], user, gitbot_tags, header=True
            )
        html += templates.get_template("nodes/item.html").render(
            {
                "item": item,
                "baker": baker,
                "node": node,
                "net": net,
                "show_bakers": show_bakers,
                "tag_found": tag_found,
                "tag_label": tag_label,
                "index": index + 1,
            }
        )

    return html


def mongo_pagination_html_header(
    total_len_rows, requested_page: int, word, len_batch=0
):
    limit = int(REQUEST_LIMIT)
    word_for_header = word.replace("_", " ")
    if total_len_rows <= int(limit):
        are = "are" if ((total_len_rows > 1) or (total_len_rows == 0)) else "is"
        s = "s" if ((total_len_rows > 1) or (total_len_rows == 0)) else ""
        html = f'<p class="small">There {are} <span id="row_count">{total_len_rows}</span> {word_for_header}{s}.</p>'
    else:
        num_of_pages = int(math.ceil(total_len_rows / limit))
        last_request_count = (min(total_len_rows, (int(num_of_pages) + 1) * limit)) - (
            (int(num_of_pages) - 1) * limit
        )
        button_postfix = f"_{word}s"

        if requested_page == -1:
            requested_page = num_of_pages - 1
        prev_string = f'<button type="button" onclick="prev_v2{button_postfix}(\'{requested_page - 1}\', \'{total_len_rows}\')" class="btn btn-sm btn-outline-primary" id="pagination"><</button>'
        if requested_page > 0:
            prev = prev_string
        elif requested_page == -1:
            prev = prev_string
        else:
            prev = ""

        next_string = f'<button type="button" onclick="next_v2{button_postfix}(\'{requested_page + 1}\', \'{total_len_rows}\')" class="btn btn-sm btn-outline-primary" id="pagination">></button>'
        if requested_page == -1:
            next = ""
        elif requested_page < (num_of_pages - 1):
            next = next_string
        else:
            next = ""

        start = (
            ""
            if requested_page == 0
            else f'<button type="button" onclick="prev_v2{button_postfix}(0, \'{total_len_rows}\')" class="btn btn-sm btn-outline-primary" id="pagination"><<</button>'
        )
        end = (
            ""
            if (requested_page == num_of_pages - 1)
            else f'<button type="button" onclick="next_v2{button_postfix}(-1, \'{total_len_rows}\')" class="btn btn-sm btn-outline-primary" id="pagination">>></button>'
        )

        count_str = f'<small>Showing {(requested_page*int(limit)+1):,.0f} to {(min(total_len_rows, (requested_page+1)*int(limit))):,.0f} from <span title="{total_len_rows}" id="row_count">{total_len_rows:,.0f}</span> {word_for_header}s</small>'

        if len_batch > 0:
            # end = ""
            count_str = f'<small>Showing {(requested_page*limit+1):,.0f} to {(min(total_len_rows, (requested_page+1)*limit)):,.0f} from <span title="{total_len_rows}" id="row_count">{total_len_rows:,.0f}</span> {word_for_header}s</small>'
            # count_str = ""

        html = (
            '<div class="clearfix">'
            f'<div style="padding-left: 10px;" class="float-start small pe-4">{count_str}</div>'
            f'<div class="float-end small pe-4">{start}{prev}{next}{end}</div>'
            "</div>"
        )
    return html


def mongo_pagination_html_header_for_account_statement(
    total_len_rows,
    requested_page: int,
    word,
    len_batch=0,
    no_more_next_page: bool = False,
):
    limit = int(REQUEST_LIMIT)
    word_for_header = word.replace("_", " ")
    button_postfix = f"_{word}s"

    # if requested_page == -1:
    #     requested_page = num_of_pages - 1
    prev_string = f'<button type="button" onclick="prev_v2{button_postfix}(\'{requested_page - 1}\')" class="btn btn-sm btn-outline-primary" id="pagination"><</button>'
    if requested_page > 0:
        prev = prev_string
    elif requested_page == -1:
        prev = prev_string
    else:
        prev = ""

    next_string = f'<button type="button" onclick="next_v2{button_postfix}(\'{requested_page + 1}\')" class="btn btn-sm btn-outline-primary" id="pagination">></button>'
    # if requested_page == -1:
    #     next = ""
    # elif requested_page < (num_of_pages - 1):
    next = next_string
    # else:
    #     next = ""
    if no_more_next_page:
        next = ""
    start = (
        ""
        if requested_page == 0
        else f'<button type="button" onclick="prev_v2{button_postfix}(0)" class="btn btn-sm btn-outline-primary" id="pagination"><<</button>'
    )

    count_str = f'<small>Showing {(requested_page*int(limit)+1):,.0f} to {(min(total_len_rows, (requested_page+1)*int(limit))):,.0f} from <span title="{total_len_rows}" id="row_count">{total_len_rows:,.0f}</span> {word_for_header}s</small>'

    if len_batch > 0:
        # end = ""
        count_str = f'<small>Showing {(requested_page*limit+1):,.0f} to {(min(total_len_rows, (requested_page+1)*limit)):,.0f} from <span title="{total_len_rows}" id="row_count">{total_len_rows:,.0f}</span> {word_for_header}s</small>'
        # count_str = ""

    html = (
        '<div class="clearfix">'
        # f'<div style="padding-left: 10px;" class="float-start small pe-4">{count_str}</div>'
        f'<div class="float-end small pe-4">{start}{next}</div>'
        "</div>"
    )
    return html


###############
# QL
###############


def ql_nodes_paging_html_header(pageInfo, len_rows, current_page, word, len_batch=0):
    limit = REQUEST_LIMIT
    if len_rows <= int(limit):
        are = "are" if ((len_rows > 1) or (len_rows == 0)) else "is"
        s = "s" if len_rows > 1 else ""
        html = f'<p class="small">There {are} <span id="row_count">{len_rows}</span> {word}{s}.</p>'
    else:
        num_of_pages = int(math.ceil(len_rows / int(limit)))
        last_request_count = (min(len_rows, (int(num_of_pages) + 1) * int(limit))) - (
            (int(num_of_pages) - 1) * int(limit)
        )
        button_postfix = f"_{word}s"
        prev = (
            f'<button type="button" onclick="prev{button_postfix}(\'{pageInfo["startCursor"]}\', \'{int(current_page) - 1}\')" class="btn btn-sm btn-outline-primary" id="pagination"><</button>'
            if pageInfo["hasPreviousPage"]
            else ""
        )
        next = (
            f'<button type="button" onclick="next{button_postfix}(\'{pageInfo["endCursor"]}\', \'{int(current_page) + 1}\')"   class="btn btn-sm btn-outline-primary" id="pagination">></button>'
            if pageInfo["hasNextPage"]
            else ""
        )
        start = (
            ""
            if not pageInfo["hasPreviousPage"]
            else f'<button type="button" onclick="prev{button_postfix}(\'first\', \'0\')" class="btn btn-sm btn-outline-primary" id="pagination"><<</button>'
        )
        end = (
            ""
            if not pageInfo["hasNextPage"]
            else f'<button type="button" onclick="next{button_postfix}(\'last: {last_request_count}\', \'{num_of_pages-1}\')" class="btn btn-sm btn-outline-primary" id="pagination">>></button>'
        )
        count_str = f'<small>Showing {(int(current_page)*int(limit)+1):,.0f} to {(min(len_rows, (int(current_page)+1)*int(limit))):,.0f} from <span title="{len_rows}" id="row_count">{len_rows:,.0f}</span> {word}s</small>'
        if len_batch > 0:
            end = ""
            count_str = f"<small>Showing {int(len_batch):,.0f} {word}s</small>"
            count_str = ""

        html = (
            '<div class="clearfix">'
            f'<div style="padding-left: 10px;" class="float-start small pe-4">{count_str}</div>'
            f'<div class="float-end small pe-4">{start}{prev}{next}{end}</div>'
            "</div>"
        )
    return html


def ql_nodes_paging_sorted_pools_html_header(
    status, key, chosen_direction, len_rows, limit, current_page
):
    # if len_rows <= int(limit):
    are = "are" if ((len_rows > 1) or (len_rows == 0)) else "is"
    s = "s" if len_rows > 1 else ""
    # html = (
    #     f'<p class="small">There {are} <span id="row_count">{len_rows}</span> pool{s}.</p>'
    # )
    # else:

    num_of_pages = int(math.ceil(len_rows / int(limit)))
    start = (
        ""
        if int(current_page) < 2
        else f'<button type="button" onclick="prev_pools({int(current_page)}, 0)" class="btn btn-sm btn-outline-primary" id="pagination"><<</button>'
    )
    prev = (
        ""
        if int(current_page) == 0
        else f'<button type="button" onclick="prev_pools({int(current_page)}, {int(current_page) - 1})" class="btn btn-sm btn-outline-primary" id="pagination"><</button>'
    )
    next = (
        ""
        if int(current_page) == (num_of_pages - 1)
        else f'<button type="button" onclick="next_pools({int(current_page)}, {int(current_page) + 1}, {len_rows})"class="btn btn-sm btn-outline-primary" id="pagination">></button>'
    )
    end = (
        ""
        if (int(current_page) >= (num_of_pages - 2))
        else f'<button type="button" onclick="next_pools({int(current_page)}, {num_of_pages - 1}, {len_rows})"class="btn btn-sm btn-outline-primary" id="pagination">>></button>'
    )
    count_str = f'<small>Showing {(int(current_page)*int(limit)+1):,.0f} to {(min(len_rows, (int(current_page)+1)*int(limit))):,.0f} from <span title="{len_rows}" id="row_count">{len_rows:,.0f}</span> pool{s}.</small>'

    html = (
        '<div class="clearfix">'
        f'<div style="padding-left: 10px;" class="float-start small pe-4">{count_str}</div>'
        f'<div class="float-end small pe-4">{start}{prev}{next}{end}</div>'
        "</div>"
    )
    html += "</p>" '<div class="float-start">'
    html += '<select class="form-select-sm" id="status" onchange="val()">'

    for stat in QLPoolStatus:
        if status == stat.name:
            html += f'<small><option class="small" value="{stat.name}" selected>{stat.value}</option></small>'
        else:
            html += f'<small><option class="small" value="{stat.name}">{stat.value}</option></small>'

    html += '</select></div><div class="float-end">'
    html += '<select class="form-select-sm" id="key" onchange="val()">'
    for sortKey in QLSortKey:
        if key == sortKey.name:
            html += f'<small><option class="small" value="{sortKey.name}" selected>{sortKey.value}</option></small>'
        else:
            html += f'<small><option class="small" value="{sortKey.name}">{sortKey.value}</option></small>'

    html += (
        "</select>" '<select class="form-select-sm" id="direction" onchange="val()">'
    )
    for direction in Direction:
        if chosen_direction == direction.name:
            html += (
                f'<option value="{direction.name}" selected>{direction.value}</option>'
            )
        else:
            html += f'<option value="{direction.name}">{direction.value}</option>'

    html += "</select></div></div><br>"
    return html


def paging_sorted_pools_html_header_v2(
    status, key, chosen_direction, requested_page, total_len_rows, word, len_batch
):
    limit = int(REQUEST_LIMIT)
    if total_len_rows <= int(limit):
        are = "are" if ((total_len_rows > 1) or (total_len_rows == 0)) else "is"
        s = "s" if total_len_rows > 1 else ""
        html = f'<p class="small">There {are} <span id="row_count">{total_len_rows}</span> {word}{s}.</p>'
    else:
        num_of_pages = int(math.ceil(total_len_rows / limit))
        last_request_count = (min(total_len_rows, (int(num_of_pages) + 1) * limit)) - (
            (int(num_of_pages) - 1) * limit
        )
        button_postfix = f"_{word}s"

        if requested_page == -1:
            requested_page = num_of_pages - 1
        prev_string = f'<button type="button" onclick="prev_v2{button_postfix}(\'{requested_page - 1}\', \'{total_len_rows}\')" class="btn btn-sm btn-outline-primary" id="pagination"><</button>'
        if requested_page > 0:
            prev = prev_string
        elif requested_page == -1:
            prev = prev_string
        else:
            prev = ""

        next_string = f'<button type="button" onclick="next_v2{button_postfix}(\'{requested_page + 1}\', \'{total_len_rows}\')" class="btn btn-sm btn-outline-primary" id="pagination">></button>'
        if requested_page == -1:
            next = ""
        elif requested_page < (num_of_pages - 1):
            next = next_string
        else:
            next = ""

        start = (
            ""
            if requested_page == 0
            else f'<button type="button" onclick="prev_v2{button_postfix}(0, \'{total_len_rows}\')" class="btn btn-sm btn-outline-primary" id="pagination"><<</button>'
        )
        end = (
            ""
            if (requested_page == num_of_pages - 1)
            else f'<button type="button" onclick="next_v2{button_postfix}(-1, \'{total_len_rows}\')" class="btn btn-sm btn-outline-primary" id="pagination">>></button>'
        )

        count_str = f'<small>Showing {(requested_page*int(limit)+1):,.0f} to {(min(total_len_rows, (requested_page+1)*int(limit))):,.0f} from <span title="{total_len_rows}" id="row_count">{total_len_rows:,.0f}</span> {word}s</small>'

        if len_batch > 0:
            # end = ""
            count_str = f'<small>Showing {(requested_page*limit+1):,.0f} to {(min(total_len_rows, (requested_page+1)*limit)):,.0f} from <span title="{total_len_rows}" id="row_count">{total_len_rows:,.0f}</span> {word.replace("_", " ")}s</small>'
            # count_str = ""

        html = (
            '<div class="clearfix">'
            f'<div style="padding-left: 10px;" class="float-start small pe-4">{count_str}</div>'
            f'<div class="float-end small pe-4">{start}{prev}{next}{end}</div>'
            "</div>"
        )
    html += "</p>" '<div class="float-start">'
    html += '<select class="form-select-sm" id="status" onchange="val()">'

    for stat in PoolStatus:
        if status == stat.name:
            html += f'<small><option class="small" value="{stat.name}" selected>{stat.value}</option></small>'
        else:
            html += f'<small><option class="small" value="{stat.name}">{stat.value}</option></small>'

    html += '</select></div><div class="float-end">'
    html += '<select class="form-select-sm" id="key" onchange="val()">'
    for sortKey in MongoSortKey:
        if key == sortKey.name:
            html += f'<small><option class="small" value="{sortKey.name}" selected>{sortKey.value}</option></small>'
        else:
            html += f'<small><option class="small" value="{sortKey.name}">{sortKey.value}</option></small>'

    html += (
        "</select>" '<select class="form-select-sm" id="direction" onchange="val()">'
    )
    for direction in Direction:
        if chosen_direction == direction.name:
            html += (
                f'<option value="{direction.name}" selected>{direction.value}</option>'
            )
        else:
            html += f'<option value="{direction.name}">{direction.value}</option>'

    html += "</select></div></div><br>"
    return html


def process_delegators_to_HTML(
    delegators, pageInfo, len_rows, current_page, user=None, tags=None
):
    html = ql_nodes_paging_html_header(pageInfo, len_rows, current_page, "delegator")
    html += '<div class="tab-pane fade show  " style="padding-top: 10px;" id="delegators" role="tabpanel" aria-labelledby="delegators-tab">'
    # for n in delegators:
    html += templates.get_template("passive/passive_delegators.html").render(
        {"delegators": delegators, "user": user, "tags": tags}
    )

    return html


def process_paydays_to_HTML(paydays, pageInfo, len_rows, current_page, nextPaydayTime):
    html = ql_nodes_paging_html_header(pageInfo, len_rows, current_page, "payday")
    html += '<div class="tab-pane fade show  " style="padding-top: 10px;" id="payday" role="tabpanel" aria-labelledby="payday-tab">'
    html += templates.get_template("staking/staking_paydays.html").render(
        {"paydays": paydays, "nextPaydayTime": nextPaydayTime}
    )

    return html


# def process_pools_to_HTML(pools, pool_rewards_list, pageInfo, len_rows, current_page):
#     html = ql_nodes_paging_html_header(
#         pageInfo, 1_000_000, current_page, "pool", len(pools)
#     )
#     html += '<div class="tab-pane fade show  " style="padding-top: 10px;" id="open" role="tabpanel" aria-labelledby="open-tab">'
#     html += templates.get_template("staking/staking_pools.html").render(
#         {"pools": pools, "pool_rewards_list": pool_rewards_list}
#     )

#     return html


# def process_sorted_pools_to_HTML(
#     pools, status, key, direction, len_rows, limit, current_page, next_page
# ):
#     html = ql_nodes_paging_sorted_pools_html_header(
#         status, key, direction, len_rows, limit, current_page
#     )
#     html += '<div class="tab-pane fade show  " style="padding-top: 10px;" id="open" role="tabpanel" aria-labelledby="open-tab">'
#     html += templates.get_template("staking/staking_pools.html").render(
#         {"pools": pools}
#     )

#     return html


def process_payday_account_rewards_to_HTML(
    request, account_rewards_list, pageInfo, len_rows, current_page, user, tags
):
    html = ql_nodes_paging_html_header(
        pageInfo, 1_000_000, current_page, "account_reward", 1
    )
    # html += '<div class="tab-pane fade show  " style="padding-top: 10px;" id="account_rewards" role="tabpanel" aria-labelledby="open-tab">'
    html += templates.get_template("/block/block_payday_account_rewards.html").render(
        {"rewards": account_rewards_list, "user": user, "tags": tags}
    )

    return html


def process_payday_account_rewards_to_HTML_v2(
    request, account_rewards_list, len_rows, requested_page, user, tags
):
    html = mongo_pagination_html_header(
        len_rows, requested_page, "account_reward", len(account_rewards_list)
    )
    html += templates.get_template("/block/block_payday_account_rewards.html").render(
        {
            "rewards": account_rewards_list,
            "user": user,
            "tags": tags,
            "request": request,
        }
    )

    return html


def process_account_statement_to_HTML_v2(
    account_statement,
    len_rows,
    requested_page,
    user,
    tags,
    previous_balance: int,
    next_balance: int,
    no_more_next_page: bool,
):
    html = mongo_pagination_html_header_for_account_statement(
        len_rows, requested_page, "entrie", len(account_statement), no_more_next_page
    )
    html += templates.get_template("/account/account_info_statement.html").render(
        {
            "account_statement": account_statement,
            "user": user,
            "tags": tags,
            "prev_balance": previous_balance,
            "next_balance": next_balance,
        }
    )

    return html


def process_paydays_to_HTML_v2(paydays_list, len_rows, requested_page, user, tags):
    html = mongo_pagination_html_header(
        len_rows, requested_page, "payday", len(paydays_list)
    )
    html += templates.get_template("staking/staking_paydays_v2.html").render(
        {
            "paydays": paydays_list,
        }
    )

    return html


def process_passive_delegators_to_HTML_v2(
    request,
    delegators_list,
    len_rows,
    requested_page,
    user,
    tags,
    delegators_current_payday_dict,
    delegators_in_block_dict,
    new_delegators,
):
    html = mongo_pagination_html_header(
        len_rows, requested_page, "passive_delegator", len(delegators_list)
    )

    html += templates.get_template("passive/passive_delegators.html").render(
        {
            "delegators": delegators_list,
            "user": user,
            "tags": tags,
            "net": "mainnet",
            "delegators_current_payday_dict": delegators_current_payday_dict,
            "delegators_in_block_dict": delegators_in_block_dict,
            "new_delegators": new_delegators,
            "request": request,
        }
    )

    return html


def process_delegators_to_HTML_v2(
    request,
    delegators_list,
    len_rows,
    requested_page,
    user,
    tags,
    delegators_current_payday_dict,
    delegators_in_block_dict,
    new_delegators,
):
    html = mongo_pagination_html_header(
        len_rows, requested_page, "delegator", len(delegators_list)
    )

    html += templates.get_template("account/account_pool_delegators.html").render(
        {
            "delegators": delegators_list,
            "user": user,
            "tags": tags,
            "net": "mainnet",
            "delegators_current_payday_dict": delegators_current_payday_dict,
            "delegators_in_block_dict": delegators_in_block_dict,
            "new_delegators": new_delegators,
            "request": request,
        }
    )

    return html


def process_tokens_to_HTML_v2(
    tokens_list, len_rows, requested_page, user, tags, net, fung_count, non_fung_count
):
    html = mongo_pagination_html_header(
        len_rows, requested_page, "token", len(tokens_list)
    )

    html += templates.get_template("account/account_tokens.html").render(
        {
            "tokens": tokens_list,
            "user": user,
            "tags": tags,
            "net": net,
            # "env": None,
            "fung_count": fung_count,
            "non_fung_count": non_fung_count,
        }
    )

    return html


def process_logged_events_to_HTML_v2(
    request,
    logged_events_list,
    len_rows,
    requested_page,
    user,
    tags,
    net,
    metadata,
    typed_tokens_tag,
    decimals,
    rewards: bool = False,
):
    html = mongo_pagination_html_header(
        len_rows,
        requested_page,
        "logged_event" if not rewards else "reward",
        len(logged_events_list),
    )

    html += templates.get_template("tokens/logged_events.html").render(
        {
            "logged_events": logged_events_list,
            "user": user,
            "tags": tags,
            "is_PTRT": rewards,
            "net": net,
            "env": request.app.env,
            "metadata": metadata,
            "typed_tokens_tag": typed_tokens_tag,
            "decimals": decimals,
            "request": request,
        }
    )

    return html


def process_summed_rewards(
    request,
    summed_rewards_dict,
    user,
    tags,
    net,
    metadata,
    typed_tokens_tag,
    decimals,
):
    html = templates.get_template("tokens/ptrt_summed_rewards.html").render(
        {
            "summed_rewards_dict": summed_rewards_dict,
            "user": user,
            "tags": tags,
            "is_PTRT": True,
            "net": net,
            "env": request.app.env,
            "metadata": metadata,
            "typed_tokens_tag": typed_tokens_tag,
            "decimals": decimals,
            "request": request,
        }
    )

    return html


def process_token_holders_to_HTML_v2(
    request,
    token_holders,
    len_rows,
    requested_page,
    user,
    tags,
    net,
    metadata,
    typed_tokens_tag,
    decimals,
):
    html = mongo_pagination_html_header(
        len_rows, requested_page, "token_holder", len(token_holders)
    )

    html += templates.get_template("tokens/token_holders.html").render(
        {
            "token_holders": token_holders,
            "user": user,
            "tags": tags,
            "net": net,
            "env": request.app.env,
            "metadata": metadata,
            "typed_tokens_tag": typed_tokens_tag,
            "decimals": decimals,
            "request": request,
        }
    )

    return html


def process_token_ids_for_tag_to_HTML_v2(
    request,
    token_ids,
    len_rows,
    requested_page,
    user,
    tags,
    net,
    metadata,
    tag,
    # decimals,
):
    html = mongo_pagination_html_header(
        len_rows, requested_page, "token_id", len(token_ids)
    )

    html += templates.get_template("tokens/token_ids.html").render(
        {
            "token_ids": token_ids,
            "user": user,
            "tags": tags,
            "net": net,
            "env": request.app.env,
            "metadata": metadata,
            "tag": tag,
            # "decimals": decimals,
            "request": request,
        }
    )

    return html


def process_payday_pool_rewards_to_HTML_v2(
    request, pool_rewards_list, len_rows, requested_page, user, tags
):
    html = mongo_pagination_html_header(
        len_rows, requested_page, "pool_reward", len(pool_rewards_list)
    )
    html += templates.get_template("/block/block_payday_pool_rewards.html").render(
        {"rewards": pool_rewards_list, "user": user, "tags": tags, "request": request}
    )

    return html


def process_classified_bakers_to_HTML_v2(
    baker_list, len_rows, requested_page, user, tags
):
    html = mongo_pagination_html_header(
        len_rows, requested_page, "pool", len(baker_list)
    )
    html += templates.get_template("staking/staking_pools_v2.html").render(
        {"pools": baker_list}
    )

    return html


def process_sorted_pools_to_HTML_v2(
    pools, status, key, direction, requested_page, total_rows
):
    html = paging_sorted_pools_html_header_v2(
        status, key, direction, requested_page, total_rows, "pool", len(pools)
    )
    html += '<div class="tab-pane fade show  " style="padding-top: 10px;" id="open" role="tabpanel" aria-labelledby="open-tab">'
    html += templates.get_template("staking/staking_pools_v2.html").render(
        {"pools": pools}
    )

    return html


def process_block_txs_to_HTML_v2(txs_list, len_rows, requested_page, user, tags):
    html = mongo_pagination_html_header(
        len_rows, requested_page, "transaction", len(txs_list)
    )
    html += templates.get_template("/block/block_payday_pool_rewards.html").render(
        {"rewards": txs_list, "user": user, "tags": tags}
    )

    return html


def process_payday_pool_rewards_to_HTML(
    pool_rewards_list, pageInfo, len_rows, current_page, user, tags, recurring
):
    html = ql_nodes_paging_html_header(
        pageInfo, 1_000_000, current_page, "pool_reward", 1
    )
    # html += '<div class="tab-pane fade show  " style="padding-top: 10px;" id="account_rewards" role="tabpanel" aria-labelledby="open-tab">'
    html += templates.get_template("/block/block_payday_pool_rewards.html").render(
        {
            "rewards": pool_rewards_list,
            "user": user,
            "tags": tags,
            "recurring": recurring,
        }
    )

    return html


def process_account_rewards_to_HTML(
    account_rewards_list, pageInfo, len_rows, current_page
):
    html = ql_nodes_paging_html_header(
        pageInfo, 1_000_000, current_page, "account_reward", 1
    )
    html += '<div class="tab-pane fade show  " style="padding-top: 10px;" id="account_rewards" role="tabpanel" aria-labelledby="open-tab">'
    html += templates.get_template("/account/account_rewards_listing.html").render(
        {"rewards": account_rewards_list}
    )

    return html


def process_account_baker_tally_to_HTML(data, pageInfo, len_rows, current_page):
    html = ql_nodes_paging_html_header(
        pageInfo, 1_000_000, current_page, "baker_tally", 1
    )
    html += '<div class="tab-pane fade show  " style="padding-top: 10px;" id="baker_tally" role="tabpanel" aria-labelledby="open-tab">'
    html += templates.get_template("/account/account_baker_tally.html").render(
        {"data": data}
    )

    return html
