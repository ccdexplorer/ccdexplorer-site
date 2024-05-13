from enum import Enum
import plotly.graph_objects as go
from ..utils import account_tag, contract_tag, convert_contract_str_to_type
from ccdexplorer_fundamentals.mongodb import MongoImpactedAddress
from ccdexplorer_fundamentals.cis import MongoTypeLoggedEvent
import math


class WhoHasLinkInfo(Enum):
    SOURCE = 0
    TARGET = 1


class NodeColors(Enum):
    ACCOUNT = "#70B785"
    SENDER_TO_ACCOUNT = "#AE7CF7"
    RECEIVER_FROM_ACCOUNT = "#549FF2"
    RECEIVER_FROM_RECEIVER_FROM_ACCOUNT = "#511FF2"
    SENDER_TO_SENDER_TO_ACCOUNT = "#549DD2"
    OTHER = "darkslategray"


class SanKey:
    def __init__(self, account_id, gte, app, token: str = None):
        self.labels = {}
        self.gte = gte
        self.colors = []
        self.target = []
        self.source = []
        self.value = []
        self.labels_link = []
        self.source_target_combo = {}
        self.graph_dict = {}
        self.app = app
        self.token = token

        self.account_id = account_id
        self.add_node(account_id, NodeColors.ACCOUNT)

    def add_node(self, node, color: NodeColors):
        # print (f"Adding {node=}, {color=}")
        if node[:29] not in self.labels.values():
            self.labels[node] = node[:29]
            self.colors.append(color.value)
            # print (f"Adding {node=} at location {list(self.labels.keys()).index(node)}, {color=}")

    def get_node_id(self, node):
        return list(self.labels.values()).index(node[:29])

    def get_source_target_id_if_exists(self, source_id, target_id):
        pass

    def add_link(self, source, target, whohaslinkinfo: WhoHasLinkInfo):
        if whohaslinkinfo == WhoHasLinkInfo.SOURCE:
            circular_link = source["account_id"] == target
        else:
            circular_link = source == target["account_id"]

        if not circular_link:
            if whohaslinkinfo == WhoHasLinkInfo.SOURCE:
                source_id = self.get_node_id(source["account_id"])
                target_id = self.get_node_id(target)
                value = source["amount"]
            else:
                source_id = self.get_node_id(source)
                target_id = self.get_node_id(target["account_id"])
                value = target["amount"]

            if (source_id, target_id) in self.source_target_combo:
                self.source_target_combo[(source_id, target_id)] = (
                    self.source_target_combo.get((source_id, target_id), 0) + value
                )
                # print (f"Updated link {source_id=} --> {target_id=} | {self.source[-1]=} --> {self.target[-1]=} with {self.value[-1]=}")
            elif (target_id, source_id) in self.source_target_combo:
                self.source_target_combo[(target_id, source_id)] = (
                    self.source_target_combo.get((target_id, source_id), 0) - value
                )
                # print (f"Updated link {source_id=} --> {target_id=} | {self.source[-1]=} --> {self.target[-1]=} with {self.value[-1]=}")
            else:
                self.source.append(source_id)
                self.target.append(target_id)
                self.value.append(value)
                self.source_target_combo[(source_id, target_id)] = value

                if whohaslinkinfo == WhoHasLinkInfo.SOURCE:
                    self.labels_link.append(source)
                else:
                    self.labels_link.append(target)
                # print (f"Add link {source_id=} --> {target_id=} | {self.source[-1]=} --> {self.target[-1]=} with {self.value[-1]=}")

    def recreate_dicts(self):
        # recreate dicts
        self.as_receiver_dict = {}
        for source_id, target_id in [
            (s, t) for (s, t) in self.source_target_combo.keys() if s != 0
        ]:
            account_id = list(self.labels.keys())[source_id]

            self.as_receiver_dict[account_id[:29]] = {
                "account_id": account_id,
                "amount": self.source_target_combo[(source_id, target_id)],
            }

        self.as_sender_dict = {}
        for source_id, target_id in [
            (s, t) for (s, t) in self.source_target_combo.keys() if t != 0
        ]:
            account_id = list(self.labels.keys())[target_id]

            self.as_sender_dict[account_id[:29]] = {
                "account_id": account_id,
                "amount": self.source_target_combo[(source_id, target_id)],
            }

    def cross_the_streams(self, user, gitbot_tags):
        """
        Method to make sure there are no negative values in the links.
        These will not show up as link in the SanKey diagram, hence
        if we find a negative link, we add an entry for the reverse
        with a positive value and delete the key for the negative value.

        For the original as_receiver_dict and as_sender_dict we need to
        perform the same actions.
        """
        keys_to_delete = []
        for source, target in list(self.source_target_combo.keys()):
            v = self.source_target_combo[(source, target)]
            if v < 0:
                self.source_target_combo[(target, source)] = -1 * v
                keys_to_delete.append((source, target))

        for key in keys_to_delete:
            del self.source_target_combo[key]

        keys_to_delete = []
        # now filter on < GTE amount
        received_other_amount = 0
        for source_id, target_id in [
            (s, t) for (s, t) in self.source_target_combo.keys() if s != 0
        ]:
            v = self.source_target_combo[(source_id, target_id)]
            if v < self.gte:
                received_other_amount += v
                keys_to_delete.append((source_id, target_id))

        if received_other_amount > 0:
            self.add_node("--->", NodeColors.OTHER)
            source_id = self.get_node_id("--->")
            target_id = self.get_node_id(self.account_id)
            self.source_target_combo[(source_id, target_id)] = received_other_amount
            # self.add_link({'amount': received_other_amount, 'account_id': 'other'}, self.account_id, WhoHasLinkInfo.SOURCE)

        sent_other_amount = 0
        for source_id, target_id in [
            (s, t) for (s, t) in self.source_target_combo.keys() if t != 0
        ]:
            v = self.source_target_combo[(source_id, target_id)]
            if v < self.gte:
                sent_other_amount += v
                keys_to_delete.append((source_id, target_id))

        if sent_other_amount > 0:
            self.add_node("<---", NodeColors.OTHER)
            source_id = self.get_node_id(self.account_id)
            target_id = self.get_node_id("<---")
            self.source_target_combo[(source_id, target_id)] = sent_other_amount
            # self.add_link(self.account_id, {'amount': sent_other_amount, 'account_id': 'other'}, WhoHasLinkInfo.TARGET)

        for key in keys_to_delete:
            del self.source_target_combo[key]

        self.recreate_dicts()
        self.fill_graph_dict()
        self.tag_the_labels(user, gitbot_tags)
        self.refill_source_target_value()
        pass

    def refill_source_target_value(self):
        self.source = [s for (s, _) in self.source_target_combo.keys()]
        self.target = [t for (_, t) in self.source_target_combo.keys()]
        self.value = [v for v in self.source_target_combo.values()]

    def tag_the_labels(self, user, gitbot_tags):
        self.tagged_labels = []
        for l in self.labels:
            if len(l) < 29:
                if l[0] == "<":
                    tag_found, tag_label = contract_tag(
                        convert_contract_str_to_type(l), None, gitbot_tags
                    )
                    if tag_found:
                        self.tagged_labels.append(tag_label)
                    else:
                        self.tagged_labels.append(l)
                else:
                    self.tagged_labels.append(l)

            else:
                tag_found, tag_label = account_tag(
                    l, user, gitbot_tags, header=True, sankey=True
                )
                if tag_found:
                    self.tagged_labels.append(tag_label)
                else:
                    if self.app:
                        if self.app.nightly_accounts_by_account_id:
                            if self.app.nightly_accounts_by_account_id.get(l[:29]):
                                value = self.app.nightly_accounts_by_account_id.get(
                                    l[:29]
                                )["index"]
                                # if not tag_found:
                                tag_label = f"👤{value}"
                                self.tagged_labels.append(tag_label)
                            else:
                                tag_label = f"👤{l[:8]}"
                                self.tagged_labels.append(l[:4])

        # as we are dumping the class Sankey to JSON, this is needed as app (fastapi) is not jsonable.
        self.app = None

    def fill_graph_dict(self):
        self.graph_dict["as_receiver_dict"] = self.as_receiver_dict
        self.graph_dict["as_sender_dict"] = self.as_sender_dict
        self.graph_dict["amount_received"] = sum(
            [x["amount"] for x in self.as_receiver_dict.values()]
        )  # self.amount_received
        self.graph_dict["amount_sent"] = sum(
            [x["amount"] for x in self.as_sender_dict.values()]
        )  # self.amount_sent
        self.graph_dict["receiver_txs"] = self.count_txs_as_receiver
        self.graph_dict["sender_txs"] = self.count_txs_as_sender
        self.graph_dict["receiver_accounts"] = len(self.as_receiver_dict)
        self.graph_dict["sender_accounts"] = len(self.as_sender_dict)

    def add_txs_for_account(
        self, txs_for_account, account_rewards_total, exchange_rates
    ):
        self.count_txs_as_receiver = 0
        self.count_txs_as_sender = 0
        self.as_receiver_dict = {}
        self.as_sender_dict = {}
        # add account rewards
        self.as_receiver_dict["Rewards"] = {
            "amount": account_rewards_total / 1_000_000,
            "account_id": "Rewards",
        }
        for ia in txs_for_account:
            ia = MongoImpactedAddress(**ia)
            if ia.balance_movement:
                if ia.balance_movement.transfer_in:
                    self.count_txs_as_receiver += 1
                    for ti in ia.balance_movement.transfer_in:
                        self.as_receiver_dict[ti.counterparty[:29]] = {
                            "amount": self.as_receiver_dict.get(
                                ti.counterparty[:29], {"amount": 0}
                            )["amount"]
                            + ti.amount / 1_000_000,
                            "account_id": ti.counterparty,
                        }
                if ia.balance_movement.transfer_out:
                    self.count_txs_as_sender += 1
                    for to in ia.balance_movement.transfer_out:
                        self.as_sender_dict[to.counterparty[:29]] = {
                            "amount": self.as_sender_dict.get(
                                to.counterparty[:29], {"amount": 0}
                            )["amount"]
                            + to.amount / 1_000_000,
                            "account_id": to.counterparty,
                        }

                if ia.balance_movement.transaction_fee:
                    self.as_sender_dict["Transaction Fees"] = {
                        "amount": self.as_sender_dict.get(
                            "Transaction Fees", {"amount": 0}
                        )["amount"]
                        + ia.balance_movement.transaction_fee / 1_000_000,
                        "account_id": "Transaction Fees",
                    }
                if ia.balance_movement.amount_encrypted:
                    self.as_sender_dict["Encrypted"] = {
                        "amount": self.as_sender_dict.get("Encrypted", {"amount": 0})[
                            "amount"
                        ]
                        + ia.balance_movement.amount_encrypted / 1_000_000,
                        "account_id": "Encrypted",
                    }
                if ia.balance_movement.amount_decrypted:
                    self.as_receiver_dict["Decrypted"] = {
                        "amount": self.as_receiver_dict.get("Decrypted", {"amount": 0})[
                            "amount"
                        ]
                        + ia.balance_movement.amount_decrypted / 1_000_000,
                        "account_id": "Decrypted",
                    }
        self.amount_received = sum(
            [x["amount"] / 1_000_000 for x in self.as_receiver_dict.values()]
        )
        self.amount_sent = sum(
            [x["amount"] / 1_000_000 for x in self.as_sender_dict.values()]
        )

        for node in [v["account_id"] for k, v in self.as_receiver_dict.items()]:
            self.add_node(node, NodeColors.SENDER_TO_ACCOUNT)

        for _, v in self.as_receiver_dict.items():
            self.add_link(v, self.account_id, WhoHasLinkInfo.SOURCE)

        for node in [v["account_id"] for k, v in self.as_sender_dict.items()]:
            self.add_node(node, NodeColors.RECEIVER_FROM_ACCOUNT)

        for _, v in self.as_sender_dict.items():
            self.add_link(self.account_id, v, WhoHasLinkInfo.TARGET)

    def add_txs_for_account_for_token(
        self,
        txs_for_account: list[MongoTypeLoggedEvent],
        decimals: int,
        display_name: str,
    ):
        self.count_txs_as_receiver = 0
        self.count_txs_as_sender = 0
        self.as_receiver_dict = {}
        self.as_sender_dict = {}
        self.display_name = display_name
        for event in txs_for_account:
            if not isinstance(event, MongoTypeLoggedEvent):
                event = MongoTypeLoggedEvent(**event)
            if event.event_type == "mint_event":
                self.count_txs_as_receiver += 1
                self.as_receiver_dict[event.contract] = {
                    "amount": self.as_receiver_dict.get(event.contract, {"amount": 0})[
                        "amount"
                    ]
                    + int(event.result["token_amount"]) * (math.pow(10, -decimals)),
                    "account_id": event.contract,
                }
            elif event.event_type == "burn_event":
                self.count_txs_as_sender += 1
                self.as_sender_dict[event.contract] = {
                    "amount": self.as_sender_dict.get(event.contract, {"amount": 0})[
                        "amount"
                    ]
                    + int(event.result["token_amount"]) * (math.pow(10, -decimals)),
                    "account_id": event.contract,
                }

            elif event.event_type == "transfer_event":
                if event.result["to_address"][:29] == self.account_id[:29]:
                    self.count_txs_as_receiver += 1
                    self.as_receiver_dict[event.result["from_address"][:29]] = {
                        "amount": self.as_receiver_dict.get(
                            event.result["from_address"][:29], {"amount": 0}
                        )["amount"]
                        + int(event.result["token_amount"]) * (math.pow(10, -decimals)),
                        "account_id": event.result["from_address"],
                    }
                elif event.result["from_address"][:29] == self.account_id[:29]:
                    self.count_txs_as_sender += 1
                    self.as_sender_dict[event.result["to_address"][:29]] = {
                        "amount": self.as_sender_dict.get(
                            event.result["to_address"][:29], {"amount": 0}
                        )["amount"]
                        + int(event.result["token_amount"]) * (math.pow(10, -decimals)),
                        "account_id": event.result["to_address"],
                    }

        self.amount_received = sum(
            [x["amount"] for x in self.as_receiver_dict.values()]
        )
        self.amount_sent = sum([x["amount"] for x in self.as_sender_dict.values()])

        for node in [v["account_id"] for k, v in self.as_receiver_dict.items()]:
            self.add_node(node, NodeColors.SENDER_TO_ACCOUNT)

        for _, v in self.as_receiver_dict.items():
            self.add_link(v, self.account_id, WhoHasLinkInfo.SOURCE)

        for node in [v["account_id"] for k, v in self.as_sender_dict.items()]:
            self.add_node(node, NodeColors.RECEIVER_FROM_ACCOUNT)

        for _, v in self.as_sender_dict.items():
            self.add_link(self.account_id, v, WhoHasLinkInfo.TARGET)

    def __repr__(self):
        return repr(self.__dict__)
