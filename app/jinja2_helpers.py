from fastapi.templating import Jinja2Templates
from app.utils import *

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["human_format"] = human_format
templates.env.filters["decide"] = decide
templates.env.filters["instance_link"] = instance_link
templates.env.filters["baker_link_with_label_no_chain"] = baker_link_with_label_no_chain
templates.env.filters["apy_perc"] = apy_perc
templates.env.filters["sort_account_rewards"] = sort_account_rewards
templates.env.filters["datetime_format"] = datetime_format
templates.env.filters["datetime_format_schedule"] = datetime_format_schedule
templates.env.filters["commafy"] = commafy
templates.env.filters["baker_ccd"] = baker_ccd
templates.env.filters["ccd_amount"] = ccd_amount
templates.env.filters["thousands"] = thousands
templates.env.filters["shorten_address"] = shorten_address
templates.env.filters["decode_memo"] = decode_memo
templates.env.filters["strip_message"] = strip_message
templates.env.filters["creation_date"] = creation_date
templates.env.filters["prob"] = prob
templates.env.filters["uptime"] = uptime
templates.env.filters["block_compare"] = block_compare
templates.env.filters["datetime_format_schedule_node"] = datetime_format_schedule_node
templates.env.filters["datetime_delta_format_schedule_node"] = (
    datetime_delta_format_schedule_node
)
templates.env.filters["sort_finalizers"] = sort_finalizers
templates.env.filters["sort_finalizers_v2"] = sort_finalizers_v2
templates.env.filters["sort_delegators"] = sort_delegators
templates.env.filters["prepare_title"] = prepare_title
templates.env.filters["regular_datetime_format"] = regular_datetime_format

templates.env.filters["ccd_per_euro"] = ccd_per_euro
templates.env.filters["round_1_decimal_no_comma"] = round_1_decimal_no_comma
templates.env.filters["datetime_format_isoparse"] = datetime_format_isoparse
templates.env.filters["datetime_format_isoparse_day_only"] = (
    datetime_format_isoparse_day_only
)
templates.env.filters["datetime_timestamp_reporting"] = datetime_timestamp_reporting
templates.env.filters["reporting_number"] = reporting_number
templates.env.filters["round_0_decimal_with_comma"] = round_0_decimal_with_comma
templates.env.filters["tx_hash_link"] = tx_hash_link
templates.env.filters["block_height_link"] = block_height_link
templates.env.filters["account_link"] = account_link
templates.env.filters["instance_link_from_str"] = instance_link_from_str

templates.env.filters["baker_link_with_label"] = baker_link_with_label

templates.env.filters["token_amount_using_decimals"] = token_amount_using_decimals
templates.env.filters["token_amount"] = token_amount
templates.env.filters["lp"] = lp
templates.env.filters["find_baker_node_info"] = find_baker_node_info
templates.env.filters["ql_apy_perc"] = ql_apy_perc

templates.env.filters["round_x_decimal_no_comma"] = round_x_decimal_no_comma
templates.env.filters["subscription_end_date"] = subscription_end_date
templates.env.filters["subscription_start_date"] = subscription_start_date
templates.env.filters["datetime_format_day_only"] = datetime_format_day_only
templates.env.filters["expectation_view"] = expectation_view
templates.env.filters["datetime_delta_format_since"] = datetime_delta_format_since
templates.env.filters["expectation"] = expectation
templates.env.filters["dec_smaller"] = dec_smaller
templates.env.filters["micro_ccd_display"] = micro_ccd_display
templates.env.filters["micro_ccd_no_decimals"] = micro_ccd_no_decimals

templates.env.filters["earliest"] = earliest
templates.env.filters["getattr"] = getattr
templates.env.filters["format_preference_key"] = format_preference_key
templates.env.filters["address_to_index"] = address_to_index
