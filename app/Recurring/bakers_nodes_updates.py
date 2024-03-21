from app.console import console
from app.classes.Enums import *
from app.classes.Node_Baker import *

from ccdexplorer_fundamentals.node import ConcordiumNodeFromDashboard

from ccdexplorer_fundamentals.mongodb import MongoDB, Collections, MongoTypePayday

# from typing import TYPE_CHECKING

# if TYPE_CHECKING:
#     from app.Recurring.recurring import Recurring


class Mixin:
    def refresh_nodes_from_collection(self):
        self.all_nodes = list(
            self.mongodb.mainnet[Collections.dashboard_nodes].find({})
        )
        all_bakers = [
            x for x in self.mongodb.mainnet[Collections.paydays_current_payday].find({})
        ]

        self.all_nodes_by_node_id = {x["nodeId"]: x for x in self.all_nodes}
        self.all_bakers_by_baker_id = {x["baker_id"]: x for x in all_bakers}

        self.baker_nodes_by_baker_id = {
            x["consensusBakerId"]: {
                "node": ConcordiumNodeFromDashboard(**x),
                "baker": self.all_bakers_by_baker_id[str(x["consensusBakerId"])],
            }
            for x in self.all_nodes
            if x["consensusBakerId"] is not None
            if str(x["consensusBakerId"]) in self.all_bakers_by_baker_id.keys()
        }

        self.baker_nodes_by_account_id = {
            self.all_bakers_by_baker_id[str(x["consensusBakerId"])]["pool_status"][
                "address"
            ]: {
                "node": ConcordiumNodeFromDashboard(**x),
                "baker": self.all_bakers_by_baker_id[str(x["consensusBakerId"])],
            }
            for x in self.all_nodes
            if x["consensusBakerId"] is not None
            if str(x["consensusBakerId"]) in self.all_bakers_by_baker_id.keys()
        }

        self.non_baker_nodes_by_node_id = {
            x["nodeId"]: {"node": ConcordiumNodeFromDashboard(**x), "baker": None}
            for x in self.all_nodes
            if x["consensusBakerId"] is None
        }

        self.non_reporting_bakers_by_baker_id = {
            x["baker_id"]: {
                "node": None,
                "baker": self.all_bakers_by_baker_id[str(x["baker_id"])],
            }
            for x in all_bakers
            if x["baker_id"] not in self.baker_nodes_by_baker_id.keys()
        }

        self.non_reporting_bakers_by_account_id = {
            self.all_bakers_by_baker_id[x["baker_id"]]["pool_status"]["address"]: {
                "node": None,
                "baker": self.all_bakers_by_baker_id[str(x["baker_id"])],
            }
            for x in all_bakers
            if x["baker_id"] not in self.baker_nodes_by_baker_id.keys()
        }
        pass

    def sort_nodes_from_class(
        self, key: str = "nodeName", direction: str = "ascending"
    ):
        reverse = True if direction == "descending" else False
        to_sort = self.list_to_sort
        if key in [
            "total_stake",
            "delegated_stake",
            "total_balance",
            "baker_id",
            "lottery_power",
        ]:
            to_sort = list(self.baker_nodes_by_baker_id.values()) + list(
                self.non_reporting_bakers_by_baker_id.values()
            )

            show_bakers_only = True
        else:
            to_sort = self.list_to_sort
            show_bakers_only = False
        try:
            # baker
            if key == SortKey.total_stake.name:
                sorted_items = sorted(
                    to_sort, key=lambda x: (x["baker"]["expectation"]), reverse=reverse
                )

            if key == SortKey.delegated_stake.name:
                sorted_items = sorted(
                    to_sort,
                    key=lambda x: (
                        x["baker"]["pool_status"]["current_payday_info"][
                            "delegated_capital"
                        ]
                    ),
                    reverse=reverse,
                )
            # if key == SortKey.client.name:
            #     sorted_items = sorted(
            #         to_sort, key=attrgetter("client"), reverse=reverse
            #     )
            if key == SortKey.baker_id.name:
                sorted_items = sorted(
                    to_sort,
                    key=lambda x: (int(x["baker"]["baker_id"])),
                    reverse=reverse,
                )
            # if key == SortKey.lottery_power.name:
            #     sorted_items = sorted(
            #         to_sort,
            #         key=attrgetter(
            #             "via_client.accountBakerPoolStatus.currentPaydayStatus.lotteryPower"
            #         ),
            #         reverse=reverse,
            #     )
            # if key == SortKey.total_balance.name:
            #     sorted_items = sorted(
            #         to_sort, key=attrgetter("via_client.accountAmount"), reverse=reverse
            #     )
            # # node
            # # if key == SortKey.ping.name:                         sorted_items = sorted(to_sort, key=attrgetter('averagePing'), reverse=reverse)
            # if key == SortKey.uptime.name:
            #     sorted_items = sorted(
            #         to_sort, key=attrgetter("uptime"), reverse=reverse
            #     )
            # if key == SortKey.nodeName.name:
            #     sorted_items = sorted(
            #         to_sort, key=attrgetter("nodeName"), reverse=reverse
            #     )
            # if key == SortKey.finalizer.name:
            #     sorted_items = sorted(
            #         to_sort,
            #         key=attrgetter("finalizationCommitteeMember"),
            #         reverse=reverse,
            #     )
            # if key == SortKey.peer_count.name:
            #     sorted_items = sorted(
            #         to_sort, key=attrgetter("peersCount"), reverse=reverse
            #     )

            # if key == SortKey.credential_creation_date.name:     sorted_items = sorted(to_sort, key=lambda item:item.baker.credential_creation_date, reverse=reverse)
        except Exception as e:
            sorted_items = to_sort
            console.log(f"Sorting Nodes Exception: {e}")
        self.sorted_nodes = sorted_items

    def set_baker_status(self):
        """
        This sets the inactive, active and not reporting lists.
        Note that can only run after get_bakers (historic bakers), request_bakers (active bakers),
        and get_nodes_to_class (nodes, so reporting).
        """
        console.log("Set baker status...")
        self.bakers_classified = {}
        self.bakers_classified[BakerStatus.Active] = set(
            self.concordium_nodes_by_baker_id.keys()
        )
        self.bakers_classified[BakerStatus.Not_Reporting] = self.bakers_classified[
            BakerStatus.Active
        ] - set(self.concordium_nodes_by_baker_id.keys())
        self.count_active_bakers = len(self.bakers_classified[BakerStatus.Active])

    def dict_to_df(self):
        the_list = []
        for ql_id in self.pools_dict.keys():
            row = self.pools_dict[ql_id]
            dd = {
                "ql_id": ql_id,
                "bakerId": row["bakerId"],
                "last24_hoursBakerReward": row["LAST24_HOURS"]["sumBakerRewardAmount"],
                "last24_hoursDelegatorsReward": row["LAST24_HOURS"][
                    "sumDelegatorsRewardAmount"
                ],
                "last24_hoursTotalReward": row["LAST24_HOURS"]["sumTotalRewardAmount"],
                "last7_daysBakerReward": row["LAST7_DAYS"]["sumBakerRewardAmount"],
                "last7_daysDelegatorsReward": row["LAST7_DAYS"][
                    "sumDelegatorsRewardAmount"
                ],
                "last7_daysTotalReward": row["LAST7_DAYS"]["sumTotalRewardAmount"],
                "last30_daysBakerReward": row["LAST30_DAYS"]["sumBakerRewardAmount"],
                "last30_daysDelegatorsReward": row["LAST30_DAYS"][
                    "sumDelegatorsRewardAmount"
                ],
                "last30_daysTotalReward": row["LAST30_DAYS"]["sumTotalRewardAmount"],
            }
            ee = {
                "stakedAmount": (
                    row["state"]["stakedAmount"]
                    if "stakedAmount" in row["state"].keys()
                    else 0
                ),
                "openStatus": (
                    row["state"]["pool"]["openStatus"]
                    if "stakedAmount" in row["state"].keys()
                    else ""
                ),
                "metadataUrl": (
                    row["state"]["pool"]["metadataUrl"]
                    if "stakedAmount" in row["state"].keys()
                    else ""
                ),
                "delegatorCount": (
                    row["state"]["pool"]["delegatorCount"]
                    if "stakedAmount" in row["state"].keys()
                    else 0
                ),
                "delegatedStake": (
                    row["state"]["pool"]["delegatedStake"]
                    if "stakedAmount" in row["state"].keys()
                    else 0
                ),
                "delegatedStakeCap": (
                    row["state"]["pool"]["delegatedStakeCap"]
                    if "stakedAmount" in row["state"].keys()
                    else 0
                ),
                "ranking_rank": (
                    row["state"]["pool"]["rankingByTotalStake"]["rank"]
                    if "stakedAmount" in row["state"].keys()
                    else 0
                ),
                "ranking_total_bakers": (
                    row["state"]["pool"]["rankingByTotalStake"]["total"]
                    if "stakedAmount" in row["state"].keys()
                    else 0
                ),
                "totalStake": (
                    row["state"]["pool"]["totalStake"]
                    if "stakedAmount" in row["state"].keys()
                    else 0
                ),
                "totalStakePercentage": (
                    row["state"]["pool"]["totalStakePercentage"]
                    if "stakedAmount" in row["state"].keys()
                    else 0
                ),
                "finalizationCommission": (
                    row["state"]["pool"]["commissionRates"]["finalizationCommission"]
                    if "stakedAmount" in row["state"].keys()
                    else 0
                ),
                "transactionCommission": (
                    row["state"]["pool"]["commissionRates"]["transactionCommission"]
                    if "stakedAmount" in row["state"].keys()
                    else 0
                ),
                "bakingCommission": (
                    row["state"]["pool"]["commissionRates"]["bakingCommission"]
                    if "stakedAmount" in row["state"].keys()
                    else 0
                ),
                "apy_30_baker": (
                    row["state"]["pool"]["apy_30"]["bakerApy"]
                    if (
                        ("stakedAmount" in row["state"].keys())
                        and (row["state"]["pool"]["apy_30"]["bakerApy"]) is not None
                    )
                    else 0
                ),
                "apy_30_delegators": (
                    row["state"]["pool"]["apy_30"]["delegatorsApy"]
                    if (
                        ("stakedAmount" in row["state"].keys())
                        and (row["state"]["pool"]["apy_30"]["delegatorsApy"])
                        is not None
                    )
                    else 0
                ),
                "apy_30_total": (
                    row["state"]["pool"]["apy_30"]["totalApy"]
                    if (
                        ("stakedAmount" in row["state"].keys())
                        and (row["state"]["pool"]["apy_30"]["totalApy"]) is not None
                    )
                    else 0
                ),
                "apy_7_baker": (
                    row["state"]["pool"]["apy_7"]["bakerApy"]
                    if (
                        ("stakedAmount" in row["state"].keys())
                        and (row["state"]["pool"]["apy_7"]["bakerApy"]) is not None
                    )
                    else 0
                ),
                "apy_7_delegators": (
                    row["state"]["pool"]["apy_7"]["delegatorsApy"]
                    if (
                        ("stakedAmount" in row["state"].keys())
                        and (row["state"]["pool"]["apy_7"]["delegatorsApy"]) is not None
                    )
                    else 0
                ),
                "apy_7_total": (
                    row["state"]["pool"]["apy_7"]["totalApy"]
                    if (
                        ("stakedAmount" in row["state"].keys())
                        and (row["state"]["pool"]["apy_7"]["totalApy"]) is not None
                    )
                    else 0
                ),
                "delegationPercentage": (
                    (
                        row["state"]["pool"]["delegatedStake"]
                        / row["state"]["pool"]["delegatedStakeCap"]
                    )
                    if (
                        ("stakedAmount" in row["state"].keys())
                        and row["state"]["pool"]["delegatedStakeCap"] > 0
                    )
                    else 0
                ),
            }
            dd.update(ee)
            the_list.append(dd)
        self.pool_list = the_list
