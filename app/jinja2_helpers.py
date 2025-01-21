from fastapi.templating import Jinja2Templates
import datetime as dt
from app.utils import *  # noqa: F403

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["datetime_format_day_only_from_ms_timestamp"] = (
    datetime_format_day_only_from_ms_timestamp  # noqa: F405
)
templates.env.filters["hex_to_rgba"] = hex_to_rgba  # noqa: F405
templates.env.filters["token_value_no_decimals"] = token_value_no_decimals  # noqa: F405
templates.env.filters["uptime"] = uptime  # noqa: F405
templates.env.filters["round_x_decimal_with_comma"] = (
    round_x_decimal_with_comma  # noqa: F405
)
templates.env.filters["round_x_decimal_no_comma"] = (
    round_x_decimal_no_comma  # noqa: F405
)
templates.env.filters["lottery_power"] = lottery_power  # noqa: F405
templates.env.filters["datetime_delta_format_since"] = (
    datetime_delta_format_since  # noqa: F405
)
templates.env.filters["datetime_delta_format_between_dates"] = (
    datetime_delta_format_between_dates  # noqa: F405
)
templates.env.filters["datetime_delta_format_since_parse"] = (
    datetime_delta_format_since_parse  # noqa: F405
)
templates.env.filters["datetime_delta_format_until"] = (
    datetime_delta_format_until  # noqa: F405
)
templates.env.filters["instance_link_from_str"] = instance_link_from_str  # noqa: F405

templates.env.filters["split_into_url_slug"] = split_into_url_slug  # noqa: F405
templates.env.filters["token_amount_using_decimals"] = (
    token_amount_using_decimals  # noqa: F405
)
templates.env.filters["token_amount_using_decimals_rounded"] = (
    token_amount_using_decimals_rounded  # noqa: F405
)
templates.env.filters["from_address_to_index"] = from_address_to_index  # noqa: F405
templates.env.filters["apy_perc"] = apy_perc  # noqa: F405


templates.env.filters["cooldown_string"] = cooldown_string  # noqa: F405
templates.env.filters["datetime_regular"] = datetime_regular  # noqa: F405
templates.env.filters["datetime_regular_parse"] = datetime_regular_parse  # noqa: F405
templates.env.filters["micro_ccd_display"] = micro_ccd_display  # noqa: F405
templates.env.filters["tx_type_translator"] = tx_type_translator  # noqa: F405
templates.env.filters["account_link"] = account_link  # noqa: F405
templates.env.filters["block_height_link"] = block_height_link  # noqa: F405
templates.env.filters["block_hash_link"] = block_hash_link  # noqa: F405
templates.env.filters["tx_hash_link"] = tx_hash_link  # noqa: F405
templates.env.filters["shorten_address"] = shorten_address  # noqa: F405
templates.env.filters["micro_ccd_no_decimals"] = micro_ccd_no_decimals  # noqa: F405
templates.env.filters["expectation_view"] = expectation_view  # noqa: F405
templates.env.filters["format_preference_key"] = format_preference_key  # noqa: F405
templates.env.filters["user_string"] = user_string  # noqa: F405
templates.env.filters["split_contract_into_url_slug_and_token_id"] = (
    split_contract_into_url_slug_and_token_id  # noqa: F405
)
templates.env.filters["none"] = none  # noqa: F405
