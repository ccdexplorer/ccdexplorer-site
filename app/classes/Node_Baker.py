from enum import Enum
from lib2to3.pytree import Node
from app.jinja2_helpers import *
from app.env import *
import numpy as np

# from app.classes.dressingroom import DressingRoom


class BakerStatus(Enum):
    """
    Bakers can be active or inactive and reporting or not reporting
    to the dashboard.
    """

    # Inactive                = 'Previously active as a baker'
    Active = "Active as a baker"
    Not_Reporting = "Active but not reporting to dashboard"


class Node:
    """
    On a schedule, we request all nodes from the Dashboard.
    We store a dictionary of nodes, keyed by nodeId, in the Chain object.
    If a node is also a baker, the Baker object gets added.
    We also store a dictionay of bakers, keyed by baker_id, in the Chain object.
    """

    def __init__(self, dct, lastBlockHeight, dict_bakers_from_accounts, reporting=True):
        self.dct = dct
        self.reporting = reporting
        if reporting:
            self.node_id = dct["nodeId"]
            self.node_name = dct["nodeName"]
            self.finalized_block_height = dct["finalizedBlockHeight"]
            self.finalized_block = dct["finalizedBlock"]
            self.finalized_time = dct["finalizedTime"]
            self.peers_count = dct["peersCount"]
            self.peers_list = dct["peersList"]
            self.client = dct["client"]
            self.uptime = dct["uptime"]
            self.str_uptime = self.get_str_uptime(self.uptime)
            self.ping = dct["averagePing"] if dct["averagePing"] else np.inf
            self.str_ping = self.get_str_ping(self.ping)
            self.str_status = self.get_node_status(
                dct["finalizedBlockHeight"], lastBlockHeight
            )

            # try to add Baker. Returns a Baker object or None.
            self.baker = Baker().from_node(dct, dict_bakers_from_accounts)

    def get_str_ping(self, value):
        value = float(str(value).replace(",", ""))
        if value == np.inf:
            return "∞ ms"
        if value > 1000:
            return f"{(value/1000):,.2f} s"
        else:
            return f"{(value):,.2f} ms"

    def get_str_uptime(self, value):
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

    def get_node_status(self, nodeLastBlockHeight, chainLastBlockHeight):
        if (chainLastBlockHeight - nodeLastBlockHeight) < 5:
            return "✅"
        else:
            return (
                f"❌ {(chainLastBlockHeight-nodeLastBlockHeight):,.0f} blocks behind."
            )


class Baker:
    def __init__(self):
        self.total_balance = 0
        self.staked_amount = 0
        self.delegated_stake = 0
        self.total_stake = 0
        self.delegator_count = 0
        self.pool_status = ""
        self.restake_earnings = False
        self.finalizer = False
        self.credential_count = 0
        self.accurate_lp = 0
        self.prob_at_least_1_block_per_day = 0
        self.active = False

    def get_binomial_prob(self, lp):
        return 1.0 - (1 - 1 / 40) ** (lp * 345600)

    def from_node(self, dct, dict_bakers_from_accounts):
        """
        This method returns the Baker object if the node is a baker,
        otherwise it returns None.
        """
        if dct["consensusBakerId"] is None:
            return None
        else:
            self.baker_id = dct["consensusBakerId"]
            # If we can find the baker id in the daily accounts list, return the account_id, otherwise None
            self.account_id = dict_bakers_from_accounts.get(
                self.baker_id, {"account": None}
            )["account"]
            return self

    def first_entry(self, baker_id, account_id, dict_first_entry):
        self.baker_id = baker_id
        self.account_id = account_id
        self.first_entry = dict_first_entry.get(self.account_id, {"date": None})["date"]
        return self

    def add_accountInfo_from(
        self, accountInfo, chain_total_balance, chain_total_staked
    ):
        if accountInfo:
            self.account_id = accountInfo["address"]["asString"]
            self.total_balance = int(accountInfo["amount"])
            if accountInfo["baker"]:
                if "pendingChange" in accountInfo["baker"]["state"]:
                    self.pending_change = accountInfo["baker"]["state"]["pendingChange"]

                if "stakedAmount" in accountInfo["baker"]["state"]:
                    self.staked_amount = int(
                        accountInfo["baker"]["state"]["stakedAmount"]
                    )
                    self.pool_status = accountInfo["baker"]["state"]["pool"][
                        "openStatus"
                    ]
                    self.delegator_count = int(
                        accountInfo["baker"]["state"]["pool"]["delegatorCount"]
                    )
                    self.delegated_stake = int(
                        accountInfo["baker"]["state"]["pool"]["delegatedStake"]
                    )
                    self.total_stake = int(
                        accountInfo["baker"]["state"]["pool"]["totalStake"]
                    )
                    self.restake_earnings = accountInfo["baker"]["state"][
                        "restakeEarnings"
                    ]
                    self.finalizer = self.total_stake > (
                        0.001 * chain_total_balance * 1_000_000
                    )
                # self.credential_count   = len(accountInfo['accountCredentials'])
                self.accurate_lp = self.total_stake / (chain_total_staked * 1_000_000)
                self.prob_at_least_1_block_per_day = self.get_binomial_prob(
                    self.accurate_lp
                )

    def add_info_from_node_summary(self, node):
        self.node = node

    # def get_ql_baking_rewards(self, stake_per_day, rewards, total_balance, total_staked):

    #     if stake_per_day:
    #         df_rewards = pd.DataFrame.from_dict(rewards['buckets'])
    #         df_rewards['date'] = pd.to_datetime(df_rewards['x_Time'], utc = True).dt.strftime('%Y-%m-%d')

    #         df_stake_per_day = pd.DataFrame.from_dict(stake_per_day)
    #         df_stake_per_day['date'] = pd.to_datetime(df_stake_per_day['date'], utc = True).dt.strftime('%Y-%m-%d')
    #         the_merge = pd.concat([df_rewards.set_index('date'),df_stake_per_day.set_index('date')], axis=1, join='outer').reset_index()
    #         the_merge['apy_estimate'] = ((the_merge['y_SumRewards'] / 1_000_000) / the_merge['staked_amount']) * 365.25
    #         the_merge.set_index('date', inplace=True)

    #         self.total_baking_rewards = rewards['sumRewardAmount']
    #         self.real_apy_period = (self.total_baking_rewards/1_000_000 / the_merge['staked_amount'].mean()) * (365.25 / 30)
    #         # self.baking_rewards_per_month = sorted_months
    #         self.apy_estimates = the_merge.to_dict('index')
    #     else:
    #         self.total_baking_rewards = 0
    #         self.apy_estimates = {}


# class Direction(Enum):
#     ascending   = 'Ascending'
#     descending  = 'Descending'
