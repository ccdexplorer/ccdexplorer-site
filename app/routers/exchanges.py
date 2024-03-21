from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from app.jinja2_helpers import *
from app.env import *
from app.state.state import *
import datetime as dt
import pytz
from app.classes.Enums import *
from ccdexplorer_fundamentals.mongodb import MongoDB, Collections

from app.Recurring.recurring import Recurring

router = APIRouter()


def get_exchange_txs_as_receiver(
    exchanges_canonical, start_block, end_block, mongodb: MongoDB
):
    pipeline = mongodb.search_exchange_txs_as_receiver(
        exchanges_canonical, start_block, end_block
    )
    txs_as_receiver = list(
        mongodb.mainnet[Collections.involved_accounts_transfer].aggregate(pipeline)
    )
    return txs_as_receiver


def get_exchange_txs_as_sender(
    exchanges_canonical, start_block, end_block, mongodb: MongoDB
):
    pipeline = mongodb.search_exchange_txs_as_sender(
        exchanges_canonical, start_block, end_block
    )
    txs_as_sender = list(
        mongodb.mainnet[Collections.involved_accounts_transfer].aggregate(pipeline)
    )
    return txs_as_sender


@router.get("/{net}/ajax_seller_buyer_mongo/{period}", response_class=HTMLResponse)
async def request_exchanges(
    net: str,
    request: Request,
    period: str,
    recurring: Recurring = Depends(get_recurring),
    mongodb: MongoDB = Depends(get_mongo_db),
    tags: dict = Depends(get_labeled_accounts),
):
    """ """
    user: UserV2 = get_user_detailsv2(request)
    exchanges_canonical = [x[:29] for x in tags["labels"]["exchanges"].keys()]

    now = dt.datetime.now().now().astimezone(pytz.UTC)

    period = ExchangePeriod[period]
    all_txs = []
    start_time = now - dt.timedelta(hours=period.value)
    start_time_block = list(
        mongodb.mainnet[Collections.blocks]
        .find({"slot_time": {"$lt": start_time}})
        .sort("slot_time", -1)
        .limit(1)
    )
    if len(start_time_block) > 0:
        start_block = start_time_block[0]["height"]
    else:
        start_block = 0

    end_block = 1_000_000_000

    txs_as_sender = get_exchange_txs_as_sender(
        exchanges_canonical, start_block, end_block, mongodb
    )
    txs_as_receiver = get_exchange_txs_as_receiver(
        exchanges_canonical, start_block, end_block, mongodb
    )
    print(
        f"{len(txs_as_sender):,.0f} as sender, {len(txs_as_receiver):,.0f} as receiver"
    )
    # print({len(txs_as_sender) + len(txs_as_receiver)})
    all_txs.extend(txs_as_sender)
    all_txs.extend(txs_as_receiver)

    no_inter_exch_txs = [
        x
        for x in all_txs
        if not (
            (x["sender_canonical"] in exchanges_canonical)
            and (x["receiver_canonical"] in exchanges_canonical)
        )
    ]

    buyers = []
    sellers = []

    df = pd.DataFrame(no_inter_exch_txs)
    if len(df) > 0:
        f_sellers = df.receiver_canonical.isin(exchanges_canonical)
        f_buyers = df.sender_canonical.isin(exchanges_canonical)

        df_buyers_gb = df[f_buyers].groupby(["receiver_canonical"])
        df_sellers_gb = df[f_sellers].groupby(["sender_canonical"])

        buyers_address = set(df_buyers_gb.groups.keys())
        sellers_address = set(df_sellers_gb.groups.keys())

        all_addresses = list(buyers_address | sellers_address)

        for address in all_addresses:
            if address in buyers_address:
                group = df_buyers_gb.get_group(address)
                buy_sum = group.amount.sum() / 1_000_000
                bought_txs_count = len(group)
            else:
                buy_sum = 0
                bought_txs_count = 0

            if address in sellers_address:
                group = df_sellers_gb.get_group(address)
                sell_sum = group.amount.sum() / 1_000_000
                sold_txs_count = len(group)
            else:
                sell_sum = 0
                sold_txs_count = 0

            total = buy_sum - sell_sum
            if total < 0:
                seller = {
                    "address_canonical": address,
                    "total": total,
                    "bought": buy_sum,
                    "sold": sell_sum,
                    "sold_txs_count": sold_txs_count,
                    "bought_txs_count": bought_txs_count,
                }
                sellers.append(seller)
            else:
                buyer = {
                    "address_canonical": address,
                    "total": total,
                    "bought": buy_sum,
                    "sold": sell_sum,
                    "sold_txs_count": sold_txs_count,
                    "bought_txs_count": bought_txs_count,
                }
                buyers.append(buyer)
            # print (sellers)
            # print (buyers)
        sellers = sorted(sellers, key=lambda d: d["total"])
        buyers = sorted(buyers, key=lambda d: d["total"], reverse=True)
    return templates.TemplateResponse(
        "exchanges/sellers_buyers_mongo.html",
        {
            "request": request,
            "env": request.app.env,
            "net": net,
            "sellers": sellers,
            "buyers": buyers,
            "period": period,
            "user": user,
            "tags": tags,
            # "sellers_count": sellers_count, "buyers_count": buyers_count
        },
    )


@router.get("/ajax_seller_buyer/{period}", response_class=HTMLResponse)
async def request_exchanges(
    request: Request,
    period: str,
    recurring: Recurring = Depends(get_recurring),
    tags: dict = Depends(get_labeled_accounts),
):
    """ """
    user: UserV2 = get_user_detailsv2(request)
    now = dt.datetime.now().now().astimezone(pytz.UTC)

    period = ExchangePeriod[period]
    if recurring.df_all_exchange_transactions is not None:
        df = recurring.df_all_exchange_transactions.copy()
        if period != ExchangePeriod.All_time:
            df = df[df["blockSlotTime"] >= (now - dt.timedelta(hours=period.value))]
        df_sum = (
            df.groupby("combined")
            .sum()
            .reset_index()
            .sort_values("amount", ascending=False)
        )

        f_sellers = df_sum.amount > 0
        f_buyers = df_sum.amount < 0
        df_sellers = df_sum[f_sellers].head(10).to_dict("records")
        df_buyers = df_sum[f_buyers].tail(10).to_dict("records")

        # do counts of txs
        sellers_count = {}
        for sel in df_sellers:
            f_sel = df.combined == sel["combined"]
            sellers_count[sel["combined"][5:]] = len(df[f_sel])

        buyers_count = {}
        for buy in df_buyers:
            f_buy = df.combined == buy["combined"]
            buyers_count[buy["combined"][5:]] = len(df[f_buy])
    else:
        df_sellers = []
        df_buyers = []
    return templates.TemplateResponse(
        "exchanges/sellers_buyers.html",
        {
            "request": request,
            "env": request.app.env,
            "df_sellers": df_sellers,
            "df_buyers": df_buyers,
            "period": period,
            "user": user,
            "tags": tags,
            "sellers_count": sellers_count,
            "buyers_count": buyers_count,
        },
    )


@router.get("/{net}/sellers-and-buyers", response_class=HTMLResponse)
async def request_exchanges(
    net: str,
    request: Request,
    tags: dict = Depends(get_labeled_accounts),
):
    """
    Add {net}.
    """
    user: UserV2 = get_user_detailsv2(request)
    periods = [x.name for x in ExchangePeriod]
    return templates.TemplateResponse(
        "exchanges/exchanges.html",
        {
            "request": request,
            "env": request.app.env,
            "net": net,
            "periods": periods,
            "user": user,
            "tags": tags,
        },
    )
