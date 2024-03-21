# ruff: noqa: F403, F405, E402, E501

from enum import Enum
import datetime as dt
from app.env import *
from app.utils import *
from app.classes.Enums import *
from pydantic import BaseModel
from ccdexplorer_fundamentals.cns import CNSEvent, CNSDomain, CNSActions
from ccdexplorer_fundamentals.user_v2 import UserV2, NotificationPreferences
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.GRPCClient.CCD_Types import *
from ccdexplorer_fundamentals.mongodb import MongoDB, Collections
from pymongo import ReplaceOne
import typing

# from ccdexplorer_fundamentals.cis import (
#     CIS,
#     StandardIdentifiers,
#     mintEvent,
#     burnEvent,
#     transferEvent,
#     tokenMetadataEvent,
#     LoggedEvents,
#     MongoTypeTokenAddress,
#     MongoTypeLoggedEvent,
# )


class Outcome(Enum):
    success = "success"
    reject = "reject"


class EventType:
    def __init__(self, event, update, emit, logged_events: list = None):
        self.event = event
        self.update = update
        self.emit = emit
        self.logged_events: list[EventType] = logged_events

    def __repr__(self):
        return f"{self.event}, {self.update}, {self.emit}"


class TransactionClassifier(Enum):
    Transfer = "Transfers"
    Smart_Contract = "Smart Cts"
    Data_Registered = "Data"
    Baking = "Staking"
    Identity = "Identity"
    Chain = "Chain"
    Failed = "Failed"
    Unclassified = "Unclassified"


class TransactionClass(Enum):
    AccountTransaction = "account_transaction"
    CredentialDeploymentTransaction = "account_creation"
    UpdateTransaction = "update"


class TransactionClassOLD(Enum):
    AccountTransaction = "accountTransaction"
    CredentialDeploymentTransaction = "credentialDeploymentTransaction"
    UpdateTransaction = "updateTransaction"


class RequestingRoute(Enum):
    account = "account"
    block = "block"
    transaction = "transaction"
    transactions = "transactions"
    smart_contract = "smart_contract"


class MakeUpRequest(BaseModel):
    class Config:
        arbitrary_types_allowed = True

    net: str
    grpcclient: GRPCClient
    mongodb: MongoDB
    tags: Optional[dict] = None
    user: Optional[UserV2] = None
    contracts_with_tag_info: Optional[dict[str, MongoTypeTokensTag]] = None
    ccd_historical: Optional[dict[str, float]] = None
    token_addresses_with_markup: Optional[dict] = None
    credential_issuers: Optional[list] = None
    app: typing.Any = None
    requesting_route: Optional[RequestingRoute] = None


class MakeUp:
    """
    Dressing up a transaction for display.
    """

    def __init__(
        self,
        makeup_request: MakeUpRequest,
        # net: str,
        # grpcclient,
        # mongodb: MongoDB,
        # tags=None,
        # user: UserV2= None,
    ):
        self.tx_hash = None
        self.block_hash = None
        self.timestamp = None
        self.baking_reward = None
        self.contents_tag = None
        self.summary = None
        self.makeup_request = makeup_request
        self.user = makeup_request.user
        self.tags = makeup_request.tags
        # self.node = node
        self.net = makeup_request.net
        self.grpcclient = makeup_request.grpcclient
        self.mongodb = makeup_request.mongodb
        self.contracts_with_tag_info = makeup_request.contracts_with_tag_info
        self.token_addresses_with_markup = makeup_request.token_addresses_with_markup
        self.credential_issuers = makeup_request.credential_issuers
        self.db_to_use = (
            self.mongodb.testnet
            if makeup_request.net == "testnet"
            else self.mongodb.mainnet
        )
        self.cns_domain = CNSDomain()
        self.csv = {}

        self.smart_contracts_updated = []

    def prepare_for_display(self, transaction, account_id, account_view):
        self._classify_transaction(transaction, account_id, account_view=account_view)

        return self

    def set_cns_action_message(self, effect_updated: CCD_InstanceUpdatedEvent):
        if effect_updated.receive_name == "BictoryCns.register":
            self.amount = self.cns_domain.amount - self.amount
            self.cns_domain.action_message = f'Registered <b>{self.cns_domain.domain_name}</b> for <b>{self.cns_domain.duration_years}</b> year{"s" if self.cns_domain.duration_years > 1 else ""}'  # at {self.cns_domain.register_address}'

        if effect_updated.receive_name == "BictoryCns.extend":
            self.cns_domain.action_message = f'Extended <b>{self.cns_domain.domain_name}</b> for <b>{self.cns_domain.duration_years}</b> year{"s" if self.cns_domain.duration_years > 1 else ""}'

        if effect_updated.receive_name == "BictoryCns.createSubdomain":
            self.amount = self.cns_domain.amount - self.amount
            self.cns_domain.action_message = f"Sub domain <b>{self.cns_domain.subdomain }</b> created on <b>{self.cns_domain.domain_name}</b>"

        if effect_updated.receive_name == "BictoryCns.setAddress":
            self.cns_domain.action_message = f"Address (to {account_link(self.cns_domain.set_address, self.net, nothing_=True, from_=False, user=self.user, tags=self.tags, white_text=True, app=self.makeup_request.app)}) set on <b>{self.cns_domain.domain_name}.</b>"

        if effect_updated.receive_name == "BictoryCns.setData":
            self.cns_domain.action_message = f"Data ({self.cns_domain.set_data_key}: {self.cns_domain.set_data_value}) set on <b>{self.cns_domain.domain_name}</b>."

        if effect_updated.receive_name == "BictoryCnsNft.transfer":
            self.cns_domain.action_message = f"<b>Transferred {self.cns_domain.domain_name}</b> to {account_link(self.cns_domain.transfer_to, self.net, nothing_=True, from_=False, user=self.user, tags=self.tags, white_text=True, app=self.makeup_request.app)}"

        if effect_updated.receive_name == "BictoryNftAuction.bid":
            self.cns_domain.action_message = f"Bid placed on <b>{self.cns_domain.domain_name}</b> for <b>{micro_ccd_no_decimals(self.cns_domain.amount)}</b>"

        if effect_updated.receive_name == "BictoryNftAuction.cancel":
            self.cns_domain.action_message = (
                f"Auction cancelled for <b>{self.cns_domain.domain_name}</b>"
            )

        if effect_updated.receive_name == "BictoryNftAuction.finalize":
            if self.cns_domain.cns_event == CNSEvent.FinalizeEvent:
                self.cns_domain.action_message = (
                    f"Auction finalized for <b>{self.cns_domain.domain_name}</b>"
                )

            if self.cns_domain.cns_event == CNSEvent.AbortEvent:
                self.cns_domain.action_message = (
                    f"Auction aborted for <b>{self.cns_domain.domain_name}</b>"
                )

            if self.cns_domain.cns_event == CNSEvent.CancelEvent:
                self.cns_domain.action_message = (
                    f"Auction cancelled for <b>{self.cns_domain.domain_name}</b>"
                )

    def get_domain_from_collection(self):
        result = self.mongodb.mainnet[Collections.cns_domains].find_one(
            {"_id": self.cns_domain.tokenId}
        )
        if result:
            self.cns_domain.domain_name = result["domain_name"]
            print(f"Using cache for {self.cns_domain.domain_name}")
        else:
            self.cns_domain.get_cns_domain_name_v2(
                self.grpcclient, self.cns_domain.tokenId, "mainnet"
            )
            document_to_store = ReplaceOne(
                {
                    "_id": self.cns_domain.tokenId,
                },
                {
                    "_id": self.cns_domain.tokenId,
                    "domain_name": self.cns_domain.domain_name,
                },
                upsert=True,
            )
            result = self.mongodb.mainnet[Collections.cns_domains].bulk_write(
                [document_to_store]
            )
            print(f"Saving cache for {self.cns_domain.domain_name}")

    def set_possible_cns_domain_from_update(
        self, effect_updated: CCD_InstanceUpdatedEvent
    ):
        self.cns_domain = CNSDomain()
        self.cns_domain.function_calls[effect_updated.receive_name] = (
            effect_updated.parameter
        )

        if effect_updated.receive_name == "BictoryCnsNft.transfer":
            self.cns_domain.action = CNSActions.transfer
            (
                self.cns_domain.tokenId,
                self.cns_domain.transfer_to,
            ) = self.cns_domain.decode_transfer_to_from(effect_updated.parameter)

            self.get_domain_from_collection()

        if effect_updated.receive_name == "BictoryCns.register":
            self.cns_domain.amount = effect_updated.amount
            self.cns_domain.action = CNSActions.register
            (
                self.cns_domain.domain_name,
                self.cns_domain.register_address,
                self.cns_domain.duration_years,
            ) = self.cns_domain.decode_from_register(effect_updated.parameter)

        if effect_updated.receive_name == "BictoryCns.extend":
            self.cns_domain.amount = effect_updated.amount
            self.cns_domain.action = CNSActions.extend
            (
                self.cns_domain.domain_name,
                self.cns_domain.duration_years,
            ) = self.cns_domain.decode_from_extend(effect_updated.parameter)

        if effect_updated.receive_name == "BictoryCns.createSubdomain":
            self.cns_domain.action = CNSActions.createSubdomain
            self.cns_domain.amount = effect_updated.amount
            self.cns_domain.subdomain = self.cns_domain.decode_subdomain_from(
                effect_updated.parameter
            )

        if effect_updated.receive_name == "BictoryCns.setAddress":
            self.cns_domain.action = CNSActions.setAddress
            (
                self.cns_domain.domain_name,
                self.cns_domain.set_address,
            ) = self.cns_domain.decode_set_address_from(effect_updated.parameter)

        if effect_updated.receive_name == "BictoryCns.setData":
            self.cns_domain.action = CNSActions.setData
            (
                self.cns_domain.domain_name,
                self.cns_domain.set_data_key,
                self.cns_domain.set_data_value,
            ) = self.cns_domain.decode_set_data_from(effect_updated.parameter)

        if effect_updated.receive_name == "BictoryNftAuction.bid":
            self.cns_domain.action = CNSActions.bid

            if len(effect_updated.events) > 0:
                the_event = effect_updated.events[0]

                (
                    tag_,
                    contract_index,
                    contract_subindex,
                    token_id_,
                    bidder_,
                    amount_,
                ) = self.cns_domain.bidEvent(the_event)

                self.cns_domain.tokenId = token_id_
                self.cns_domain.amount = amount_

                self.get_domain_from_collection()

        if effect_updated.receive_name == "BictoryNftAuction.finalize":
            self.cns_domain.action = CNSActions.finalize

            if len(effect_updated.events) > 0:
                the_event = effect_updated.events[0]

                (
                    tag_,
                    contract_index,
                    contract_subindex,
                    token_id_,
                    seller_,
                    winner_,
                    price_,
                    seller_share,
                    royalty_length_,
                    royalties,
                    owner_,
                    bidder_,
                    amount_,
                ) = self.cns_domain.finalize(the_event)

                self.cns_domain.tokenId = token_id_

                self.get_domain_from_collection()

        if effect_updated.receive_name == "BictoryNftAuction.cancel":
            self.cns_domain.action = CNSActions.cancel

            if len(effect_updated.events) > 0:
                the_event = effect_updated.events[0]

                (
                    tag_,
                    contract_index,
                    contract_subindex,
                    token_id_,
                    owner_,
                ) = self.cns_domain.cancelEvent(the_event)

                self.cns_domain.tokenId = token_id_

                self.get_domain_from_collection()

        if effect_updated.receive_name == "BictoryCnsNft.getTokenExpiry":
            self.cns_domain.action = CNSActions.getTokenExpiry
            self.cns_domain.tokenId = self.cns_domain.decode_token_id_from(
                effect_updated.parameter
            )

            self.get_domain_from_collection()

    def set_possible_cns_domain_from_interrupt(
        self, effect_interrupted: CCD_ContractTraceElement_Interrupted
    ):
        self.cns_domain = CNSDomain()
        if len(effect_interrupted.events) > 0:
            the_event = effect_interrupted.events[0]

            (
                tag_,
                contract_index,
                contract_subindex,
                token_id_,
                seller_,
                winner_,
                price_,
                seller_share,
                royalty_length_,
                royalties,
                owner_,
                bidder_,
                amount_,
            ) = self.cns_domain.finalize(the_event)

            self.cns_domain.tokenId = token_id_

            self.get_domain_from_collection()

    def _classify_transaction(
        self, t: CCD_BlockItemSummary, account_id=None, account_view=False
    ):
        self.dct = {}
        self.tx_hash = t.hash
        self.timestamp = t.block_info.slot_time
        self.transaction = t
        self.from_account = None
        self.to_account = None
        self.amount = 0
        self.tokenId = None
        self.classifier = TransactionClassifier.Unclassified
        self.events_list = []

        if t.type.type == TransactionClass.AccountTransaction.value:
            dct = {
                "start_1": "",
                "end_1": (
                    "✅"
                    if t.account_transaction.outcome == Outcome.success.value
                    else "❌"
                ),
                "start_2": f"{datetime_delta_format_since(self.timestamp)} ago",
                "end_2": "Account Transaction",
                "start_3": tx_hash_link(t.hash, self.net),
                "end_3": cost_html(t.energy_cost, energy=True),
                "start_4": block_height_link(t.block_info.height, self.net),
                "end_4": cost_html(t.account_transaction.cost, energy=False),
                "start_5": account_link(
                    t.account_transaction.sender,
                    self.net,
                    from_=True,
                    user=self.user,
                    tags=self.tags,
                    app=self.makeup_request.app,
                ),
                "end_5": "",
                "show_table": False,
                "events": None,
                "memo": "",
                "csv_memo": "",
                "txHash": t.hash,
                "schedule": [],
            }

            if t.account_transaction.outcome == Outcome.reject.value:
                dct.update({"events": None, "memo": t.type.contents})
                new_event = EventType(f"Reason: {t.type.contents}", None, None)
                self.events_list.append(new_event)
                self.classifier = TransactionClassifier.Failed
                effects = None
            else:
                new_event = None
                effects = t.account_transaction.effects
                dct.update({"events": [1]})

                if effects.module_deployed:
                    self.classifier = TransactionClassifier.Smart_Contract
                    new_event = EventType(
                        f'Contract Module Deployed: <a href="/{self.net}/module/{effects.module_deployed}">{effects.module_deployed[:10]}</a>',
                        None,
                        None,
                    )

                elif effects.contract_initialized:
                    self.classifier = TransactionClassifier.Smart_Contract

                    logged_events = []
                    for event in effects.contract_initialized.events:
                        if (  # only look for logged events to display if we know the tag.
                            effects.contract_initialized.address.to_str()
                            in self.contracts_with_tag_info.keys()
                        ):
                            process_event_request = ProcessEventRequest(
                                **{
                                    "contract_address": effects.contract_initialized.address,
                                    "event": event,
                                    "net": self.net,
                                    "user": self.user,
                                    "tags": self.tags,
                                    "db_to_use": self.db_to_use,
                                    "contracts_with_tag_info": self.contracts_with_tag_info,
                                    # "token_addresses_with_markup": self.token_addresses_with_markup,
                                    "app": self.makeup_request.app,
                                }
                            )
                            result = process_event_for_makeup(req=process_event_request)

                            if result:
                                logged_events.append(result)

                    new_event = EventType(
                        f"Contract Initialized {instance_link_v2(effects.contract_initialized.address, self.user, self.tags, self.net)}",
                        f'Initializer: {effects.contract_initialized.init_name}<br>Module: <a href="/{self.net}/module/{effects.contract_initialized.origin_ref}">{effects.contract_initialized.origin_ref[:10]}</a>',
                        None,
                        logged_events,
                    )
                elif effects.contract_update_issued:
                    self.classifier = TransactionClassifier.Smart_Contract
                    for effect in effects.contract_update_issued.effects:
                        if effect.updated:
                            logged_events = []
                            if (  # only look for logged events to display if we know the tag.
                                effect.updated.address.to_str()
                                in self.contracts_with_tag_info.keys()
                            ) or (
                                effect.updated.address.to_str()
                                in self.credential_issuers
                            ):
                                process_events = len(effect.updated.events) < 100

                                if self.makeup_request.requesting_route:
                                    if (len(effect.updated.events) > 100) and (
                                        self.makeup_request.requesting_route
                                        == RequestingRoute.transaction
                                    ):
                                        process_events = True

                                if process_events:
                                    for event in effect.updated.events:
                                        process_event_request = ProcessEventRequest(
                                            **{
                                                "contract_address": effect.updated.address,
                                                "event": event,
                                                "net": self.net,
                                                "user": self.user,
                                                "tags": self.tags,
                                                "db_to_use": self.db_to_use,
                                                "contracts_with_tag_info": self.contracts_with_tag_info,
                                                # "token_addresses_with_markup": self.token_addresses_with_markup,
                                                "app": self.makeup_request.app,
                                            }
                                        )
                                        result = process_event_for_makeup(
                                            req=process_event_request
                                        )

                                        if result:
                                            logged_events.append(result)
                                else:
                                    logged_events.append(
                                        EventType(
                                            "Logged Events",
                                            "> 100 events...view individual tx to see details.",
                                            None,
                                        )
                                    )
                            if t.block_info.height < 6_000_000:
                                self.set_possible_cns_domain_from_update(effect.updated)
                                self.set_cns_action_message(effect.updated)
                            amount_str = (
                                f"<br>Amount: {micro_ccd_display(effect.updated.amount)}"
                                if effect.updated.amount > 0
                                else ""
                            )
                            new_event = EventType(
                                f"Updated contract with address {instance_link_v2(effect.updated.address, self.user, self.tags, self.net)}",
                                f"Contract: {effect.updated.receive_name.split('.')[0]}<br>Function: {effect.updated.receive_name.split('.')[1]}{amount_str}",
                                f"Message: {shorten_address(effect.updated.parameter)}",
                                logged_events,
                            )
                            self.smart_contracts_updated.append(effect.updated.address)

                        if effect.interrupted:
                            logged_events = []
                            if (  # only look for logged events to display if we know the tag.
                                effect.interrupted.address.to_str()
                                in self.contracts_with_tag_info.keys()
                            ):
                                for event in effect.interrupted.events:
                                    process_event_request = ProcessEventRequest(
                                        **{
                                            "contract_address": effect.interrupted.address,
                                            "event": event,
                                            "net": self.net,
                                            "user": self.user,
                                            "tags": self.tags,
                                            "db_to_use": self.db_to_use,
                                            "contracts_with_tag_info": self.contracts_with_tag_info,
                                            # "token_addresses_with_markup": self.token_addresses_with_markup,
                                            "app": self.makeup_request.app,
                                        }
                                    )
                                    result = process_event_for_makeup(
                                        req=process_event_request
                                    )

                                    if result:
                                        logged_events.append(result)

                            self.set_possible_cns_domain_from_interrupt(
                                effect.interrupted
                            )
                            new_event = EventType(
                                f"Interrupted contract with address {instance_link_v2(effect.interrupted.address, self.user, self.tags, self.net)}",
                                None,
                                None,
                                logged_events,
                            )

                        if effect.transferred:
                            new_event = EventType(
                                f"Transferred {(micro_ccd_display(effect.transferred.amount))} from {instance_link_v2(effect.transferred.sender, self.net)} to {account_link(effect.transferred.receiver, self.net, from_=False, nothing_=True, user=self.user,tags=self.tags, app=self.makeup_request.app)}",
                                None,
                                None,
                            )

                        if effect.resumed:
                            new_event = EventType(
                                f"Resumed contract with address {instance_link_v2(effect.resumed.address, self.user, self.tags, self.net)}",
                                None,
                                None,
                            )

                        if new_event:
                            self.events_list.append(new_event)

                elif effects.account_transfer:
                    self.classifier = TransactionClassifier.Transfer
                    self.amount = effects.account_transfer.amount

                    memo = (
                        f"Memo: {decode_memo(effects.account_transfer.memo)}"
                        if effects.account_transfer.memo
                        else None
                    )
                    dct.update(
                        {"start_1": effects.account_transfer.amount, "memo": memo}
                    )
                    self.to_account = effects.account_transfer.receiver
                    self.from_account = t.account_transaction.sender

                    self.to_link = account_link(
                        effects.account_transfer.receiver,
                        self.net,
                        from_=False,
                        nothing_=True,
                        user=self.user,
                        tags=self.tags,
                        app=self.makeup_request.app,
                    )

                    self.from_link = account_link(
                        t.account_transaction.sender,
                        self.net,
                        from_=True,
                        nothing_=True,
                        user=self.user,
                        tags=self.tags,
                        app=self.makeup_request.app,
                    )

                    dct.update(
                        {
                            "end_5": account_link(
                                effects.account_transfer.receiver,
                                self.net,
                                from_=False,
                                user=self.user,
                                tags=self.tags,
                                app=self.makeup_request.app,
                            ),
                        }
                    )

                    new_event = EventType(
                        f"Transferred {micro_ccd_display(effects.account_transfer.amount)} from {self.from_link} to {self.to_link}",
                        memo if memo else None,
                        None,
                    )

                elif effects.baker_added:
                    self.classifier = TransactionClassifier.Baking
                    new_event = EventType(
                        "Validator Added",
                        f"Restake Earnings: {effects.baker_added.restake_earnings}<br>Staked amount: {micro_ccd_display(effects.baker_added.stake)}",
                        None,
                    )

                elif effects.baker_removed:
                    self.classifier = TransactionClassifier.Baking
                    new_event = EventType("Validator Removed", None, None)

                elif effects.baker_stake_updated:
                    self.classifier = TransactionClassifier.Baking
                    movement_str = (
                        "Increased"
                        if effects.baker_stake_updated.update.increased
                        else "Decreased"
                    )
                    new_event = EventType(
                        f"Validator Stake {movement_str}",
                        f"New staked amount: {micro_ccd_display(effects.baker_stake_updated.update.new_stake)}",
                        None,
                    )

                elif effects.baker_restake_earnings_updated:
                    self.classifier = TransactionClassifier.Baking
                    new_event = EventType(
                        "Validator Set Restake Earnings",
                        f"Restake Earnings: {effects.baker_restake_earnings_updated.restake_earnings}",
                        None,
                    )

                elif effects.transferred_to_public:
                    new_event = EventType(
                        "Amount Transferred to Public",
                        f"Amount: {micro_ccd_display(effects.transferred_to_public.amount)}",
                        None,
                    )
                    self.events_list.append(new_event)
                    self.classifier = TransactionClassifier.Transfer

                elif effects.baker_keys_updated:
                    self.classifier = TransactionClassifier.Baking
                    new_event = EventType(
                        f"Validator Keys Updated for validator: {effects.baker_keys_updated.baker_id}",
                        None,
                        None,
                    )

                elif effects.encrypted_amount_transferred:
                    self.classifier = TransactionClassifier.Transfer
                    memo = (
                        f"Memo: {effects.encrypted_amount_transferred.memo}"
                        if effects.encrypted_amount_transferred.memo
                        else None
                    )
                    new_event = EventType(
                        "Encrypted Amount Transferred", f"{memo}", None
                    )

                elif effects.transferred_to_encrypted:
                    self.classifier = TransactionClassifier.Transfer
                    new_event = EventType(
                        "Transferred to Encrypted",
                        f"{micro_ccd_display(effects.transferred_to_encrypted.amount)}",
                        None,
                    )

                elif effects.transferred_to_public:
                    self.classifier = TransactionClassifier.Transfer
                    new_event = EventType(
                        "Transferred to Public",
                        f"{micro_ccd_display(effects.transferred_to_public.amount)}",
                        None,
                    )

                elif effects.transferred_with_schedule:
                    self.classifier = TransactionClassifier.Transfer
                    dct.update(
                        {
                            "show_table": True,
                            "schedule": effects.transferred_with_schedule.amount,
                            # 'start_1': event['totalAmount'],
                            "end_5": account_link(
                                effects.transferred_with_schedule.receiver,
                                self.net,
                                from_=False,
                                user=self.user,
                                tags=self.tags,
                                app=self.makeup_request.app,
                            ),
                        }
                    )
                    memo = (
                        f"Memo: {decode_memo(effects.transferred_with_schedule.memo)}"
                        if effects.transferred_with_schedule.memo
                        else None
                    )
                    self.to_account = effects.transferred_with_schedule.receiver
                    self.amount = sum(
                        [
                            int(x.amount)
                            for x in effects.transferred_with_schedule.amount
                        ]
                    )
                    dct.update({"start_1": self.amount})
                    new_event = EventType(
                        "Transferred with Schedule", memo if memo else None, None
                    )

                elif effects.credential_keys_updated:
                    self.classifier = TransactionClassifier.Identity
                    new_event = EventType("Credential Keys Updated", None, None)

                elif effects.credentials_updated:
                    self.classifier = TransactionClassifier.Identity
                    new_event = EventType(
                        "Credentials Updated",
                        f"New Threshold: {effects.credentials_updated.new_threshold}",
                        None,
                    )

                elif effects.baker_configured:
                    self.classifier = TransactionClassifier.Baking

                    for event in effects.baker_configured.events:
                        if event.baker_added:
                            new_event = EventType(
                                "Validator Added",
                                f"Restake Earnings: {event.baker_added.restake_earnings}<br>Staked amount: {micro_ccd_display(event.baker_added.stake)}",
                                None,
                            )

                        elif event.baker_removed is not None:
                            new_event = EventType(
                                "Validator Removed",
                                f"Validator ID: {event.baker_removed}",
                                None,
                            )

                        elif event.baker_stake_increased:
                            new_event = EventType(
                                f"Validator Stake Increased for validator: {event.baker_stake_increased.baker_id}",
                                f"New staked amount: {micro_ccd_display(event.baker_stake_increased.new_stake)}",
                                None,
                            )

                        elif event.baker_stake_decreased:
                            new_event = EventType(
                                f"Validator Stake Decreased for validator: {event.baker_stake_decreased.baker_id}",
                                f"New staked amount: {micro_ccd_display(event.baker_stake_decreased.new_stake)}",
                                None,
                            )

                        elif event.baker_restake_earnings_updated:
                            new_event = EventType(
                                f"Validator Stake Set Restake Earnings for validator: {event.baker_restake_earnings_updated.baker_id}",
                                f"Restake Earnings: {event.baker_restake_earnings_updated.restake_earnings}",
                                None,
                            )

                        elif event.baker_keys_updated:
                            new_event = EventType(
                                f"Validator Keys Updated for validator: {event.baker_keys_updated.baker_id}",
                                None,
                                None,
                            )

                        elif event.baker_set_open_status:
                            if event.baker_set_open_status.open_status == 0:
                                status = "open_for_all"
                            elif event.baker_set_open_status.open_status == 1:
                                status = "closed_for_new"
                            elif event.baker_set_open_status.open_status == 2:
                                status = "closed_for_all"

                            new_event = EventType(
                                f"Validator Set Pool Status for validator: {event.baker_set_open_status.baker_id}",
                                f"Open Status: {status}",
                                None,
                            )

                        elif event.baker_set_metadata_url:
                            new_event = EventType(
                                f"Validator Set MetaDataURL for validator: {event.baker_set_metadata_url.baker_id}",
                                f"metadataURL: <a href='{event.baker_set_metadata_url.url}'>{event.baker_set_metadata_url.url}</a>",
                                None,
                            )

                        elif event.baker_set_transaction_fee_commission:
                            new_event = EventType(
                                f"Validator Set Transaction Commission for validator: {event.baker_set_transaction_fee_commission.baker_id}",
                                f"Transaction Commission: {event.baker_set_transaction_fee_commission.transaction_fee_commission*100:,.2f}%",
                                None,
                            )

                        elif event.baker_set_baking_reward_commission:
                            new_event = EventType(
                                f"Validator Set Block Commission for validator: {event.baker_set_baking_reward_commission.baker_id}",
                                f"Block Commission: {event.baker_set_baking_reward_commission.baking_reward_commission*100:,.2f}%",
                                None,
                            )

                        elif event.baker_set_finalization_reward_commission:
                            new_event = EventType(
                                f"Validator Set Finalization Reward Commission for validator: {event.baker_set_finalization_reward_commission.baker_id}",
                                f"Finalization Reward Commission: {event.baker_set_finalization_reward_commission.finalization_reward_commission*100:,.2f}%",
                                None,
                            )

                        if new_event:
                            self.events_list.append(new_event)

                elif effects.delegation_configured:
                    self.classifier = TransactionClassifier.Baking

                    for event in effects.delegation_configured.events:
                        if event.delegation_added:
                            new_event = EventType(
                                "Delegation Added",
                                f"Delegator ID: {event.delegation_added}",
                                None,
                            )

                        elif event.delegation_removed:
                            new_event = EventType(
                                "Delegation Removed",
                                f"Delegator ID: {event.delegation_removed}",
                                None,
                            )

                        elif event.delegation_stake_increased:
                            new_event = EventType(
                                "Delegation Stake Increased",
                                f"New staked amount: {micro_ccd_display(event.delegation_stake_increased.new_stake)}",
                                None,
                            )

                        elif event.delegation_stake_decreased:
                            new_event = EventType(
                                "Delegation Stake Decreased",
                                f"New staked amount: {micro_ccd_display(event.delegation_stake_decreased.new_stake)}",
                                None,
                            )

                        elif event.delegation_set_restake_earnings:
                            new_event = EventType(
                                "Delegation Stake Set Restake Earnings",
                                f"Restake Earnings: {event.delegation_set_restake_earnings.restake_earnings}",
                                None,
                            )

                        elif event.delegation_set_delegation_target:
                            target = (
                                "Passive Delegation"
                                if event.delegation_set_delegation_target.delegation_target.passive_delegation
                                else event.delegation_set_delegation_target.delegation_target.baker
                            )
                            new_event = EventType(
                                "Delegation Set Target", f"Target: {target}", None
                            )

                        if new_event:
                            self.events_list.append(new_event)

                elif effects.data_registered is not None:
                    self.classifier = TransactionClassifier.Data_Registered
                    new_event = EventType(
                        "Data Registered",
                        None,
                        f"{shorten_address(effects.data_registered)}",
                    )

                if new_event and (len(self.events_list) == 0):
                    self.events_list.append(new_event)

            day = f"{self.timestamp:%Y-%m-%d}"
            if self.makeup_request.ccd_historical:
                ccd_historical_rate = self.makeup_request.ccd_historical.get(day)
            else:
                ccd_historical_rate = None
            ccd_amount = dct["start_1"]
            dct.update({"start_1": f"{micro_ccd_display(ccd_amount)}"})
            if effects:
                if ccd_historical_rate and (
                    effects.account_transfer or effects.transferred_with_schedule
                ):
                    dct.update(
                        {
                            "start_1": f'{dct["start_1"]} <span class="ccd small">(~{(int(ccd_amount/1_000_000) * ccd_historical_rate):,.0f} USD)</span>'
                        }
                    )
            self.dct = dct

        elif t.type.type == TransactionClass.CredentialDeploymentTransaction.value:
            self.classifier = TransactionClassifier.Identity
            self.cns_tx_message = None
            dct = {
                "start_1": "",
                "end_1": "",
                "start_2": f"{datetime_delta_format_since(self.timestamp)} ago",
                "end_2": "Account Created",
                "start_3": tx_hash_link(t.hash, self.net),
                "end_3": cost_html(t.energy_cost, energy=True),
                "start_4": block_height_link(t.block_info.height, self.net),
                "end_4": "",
                "start_5": "",
                "end_5": "",
                "show_table": False,
                "events": None,
                "memo": "",  # f'New account created: {self.get_new_address_from_events(t)}',
                "csv_memo": "",
                "schedule": [],
            }

            new_event = EventType(
                f"Account created: {account_link(t.account_creation.address, self.net,from_=False, nothing_=True, user=self.user, tags=self.tags, app=self.makeup_request.app)}",
                None,
                f"Address: {shorten_address(t.account_creation.address, address=True)}",
            )
            self.events_list.append(new_event)

            self.dct = dct
        elif t.type.type == TransactionClass.UpdateTransaction.value:
            self.classifier = TransactionClassifier.Chain
            self.cns_tx_message = None
            dct = {
                "start_1": "",
                "end_1": "",
                "start_2": f"{datetime_delta_format_since(self.timestamp)} ago",
                "end_2": "Update",
                "start_3": tx_hash_link(t.hash, self.net),
                "end_3": cost_html(t.energy_cost, energy=True),
                "start_4": block_height_link(t.block_info.height, self.net),
                "end_4": None,
                "start_5": None,
                "end_5": "",
                "show_table": False,
                "events": None,
                "memo": "",  # f'New account created: {self.get_new_address_from_events(t)}',
                "csv_memo": "",
                "schedule": [],
            }

            if t.update.effective_time:
                eff = f"{dt.datetime.fromtimestamp(t.update.effective_time):%Y-%m-%d %H:%M:%S}"
            else:
                eff = t.block_info.slot_time

            if t.update.payload.micro_ccd_per_euro_update:
                new_event = EventType(
                    "Micro CCD per EUR Update",
                    f"Effective Time: {eff}<br>New Rate: {1_000_000*(int(t.update.payload.micro_ccd_per_euro_update.denominator)/int(t.update.payload.micro_ccd_per_euro_update.numerator)):,.6f} EUR",
                    None,
                )
                self.events_list.append(new_event)

            if t.update.payload.euro_per_energy_update:
                new_event = EventType(
                    "EUR per Energy Update",
                    f"Effective Time: {eff}<br>New Rate: {1_000_000*(int(t.update.payload.euro_per_energy_update.denominator)/int(t.update.payload.euro_per_energy_update.numerator)):,.6f} EUR",
                    None,
                )
                self.events_list.append(new_event)

            if t.update.payload.mint_distribution_cpv_1_update:
                new_event = EventType(
                    "Mint Distribution Update",
                    f"Effective Time: {eff}<br>Block Reward: {(100*t.update.payload.mint_distribution_cpv_1_update.baking_reward):,.0f}%<br/>Finalization Reward: {(100*t.update.payload.mint_distribution_cpv_1_update.finalization_reward):,.0f}%",
                    None,
                )
                self.events_list.append(new_event)

            if t.update.payload.cooldown_parameters_cpv_1_update:
                new_event = EventType(
                    "Cooldown Parameters Update",
                    f"Effective Time: {eff}<br>Pool Owner Cooldown: {(t.update.payload.cooldown_parameters_cpv_1_update.pool_owner_cooldown/(60*60*24)):,.0f} days<br/>Delegator Cooldown: {(t.update.payload.cooldown_parameters_cpv_1_update.delegator_cooldown/(60*60*24)):,.0f} days",
                    None,
                )
                self.events_list.append(new_event)

            if t.update.payload.time_parameters_cpv_1_update:
                new_event = EventType(
                    "Time Parameters Update",
                    f"Effective Time: {eff}<br>New Mint rate per payday: {(t.update.payload.time_parameters_cpv_1_update.mint_per_payday.mantissa*math.pow(10, -t.update.payload.time_parameters_cpv_1_update.mint_per_payday.exponent)):,.12f}<br/>Reward period length: {t.update.payload.time_parameters_cpv_1_update.reward_period_length:,.0f} epochs",
                    None,
                )
                self.events_list.append(new_event)

            elif t.update.payload.protocol_update:
                new_event = EventType(
                    "Protocol Update",
                    f"Effective Time: {eff}<br>{t.update.payload.protocol_update.message_}<br>More info at the <a href='{t.update.payload.protocol_update.specification_url}'>Specification URL</a>.",
                    None,
                )
                self.events_list.append(new_event)

            elif t.update.payload.foundation_account_update:
                new_account = (
                    account_link(
                        t.update.payload.foundation_account_update,
                        self.net,
                        from_=True,
                        user=self.user,
                        tags=self.tags,
                        app=self.makeup_request.app,
                    ),
                )
                new_event = EventType(
                    "Foundation Account Update",
                    f"Effective Time: {eff}<br>New Account: {new_account}",
                    None,
                )
                self.events_list.append(new_event)

            elif t.update.payload.election_difficulty_update:
                new_event = EventType(
                    "Election Difficulty Update",
                    f"Effective Time: {eff}<br>Value: {t.update.payload.election_difficulty_update}",
                    None,
                )
                self.events_list.append(new_event)

            elif t.update.payload.baker_stake_threshold_update:
                new_event = EventType(
                    "Validator Stake Threshold Update",
                    f"Effective Time: {eff}<br>Threshold: {micro_ccd_display(t.update.payload.baker_stake_threshold_update.baker_stake_threshold)}",
                    None,
                )
                self.events_list.append(new_event)

            elif t.update.payload.level_1_update:
                new_event = EventType(
                    "Level 1 Keys Update",
                    f"Effective Time: {eff}<br>",
                    None,
                )
                self.events_list.append(new_event)

            elif t.update.payload.add_identity_provider_update:
                new_event = EventType(
                    "Add Identity Provider",
                    f"Effective Time: {eff}<br>Name: {t.update.payload.add_identity_provider_update.description.name}<br>Description: {t.update.payload.add_identity_provider_update.description.description}<br/>More info at: <a href='{t.update.payload.add_identity_provider_update.description.url}'>{t.update.payload.add_identity_provider_update.description.url}</a>",
                    None,
                )
                self.events_list.append(new_event)

            elif t.update.payload.finalization_committee_parameters_update:
                new_event = EventType(
                    "Finalization Committee Parameters Update",
                    f"Effective Time: {eff}<br>Minimum Finalizers: {t.update.payload.finalization_committee_parameters_update.minimum_finalizers:,.0f}<br>Maximum Finalizers: {t.update.payload.finalization_committee_parameters_update.maximum_finalizers:,.0f}<br/>Finalizers Relative Stake Threshold: {t.update.payload.finalization_committee_parameters_update.finalizer_relative_stake_threshold:,.6f}",
                    None,
                )
                self.events_list.append(new_event)

            elif t.update.payload.add_anonymity_revoker_update:
                new_event = EventType(
                    "Add Anonymity Revoker",
                    f"Effective Time: {eff}<br>Name: {t.update.payload.add_anonymity_revoker_update.description.name}<br>Description: {t.update.payload.add_anonymity_revoker_update.description.description}<br/>More info at: <a href='{t.update.payload.add_anonymity_revoker_update.description.url}'>{t.update.payload.add_anonymity_revoker_update.description.url}</a>",
                    None,
                )
                self.events_list.append(new_event)

            elif t.update.payload.pool_parameters_cpv_1_update:
                pp = t.update.payload.pool_parameters_cpv_1_update
                new_event = EventType(
                    "Pool Parameters Update",
                    f"""
                    Effective Time: {eff}<br>
                    <table class='table table-sm'>
                    <tr><td>Block Commission Range:</td><td class='text-end'>{(pp.commission_bounds.baking.min*100):,.0f}% - {(pp.commission_bounds.baking.max_*100):,.0f}%</td></tr>
                    <tr><td>Finalization Commission Range:</td><td class='text-end'>{(pp.commission_bounds.finalization.min*100):,.0f}% - {(pp.commission_bounds.finalization.max_*100):,.0f}%</td></tr>
                    <tr><td>Transaction Commission Range:</td><td class='text-end'>{(pp.commission_bounds.transaction.min*100):,.0f}% - {(pp.commission_bounds.transaction.max_*100):,.0f}%</td></tr>
                    <tr><td>Passive Block Commission:</td><td class='text-end'>{(pp.passive_baking_commission*100):,.0f}%</td></tr>
                    <tr><td>Passive Transaction Commission:</td><td class='text-end'>{(pp.passive_transaction_commission*100):,.0f}%</td></tr>
                    <tr><td>Passive Finalization Commission:</td><td class='text-end'>{(pp.passive_finalization_commission*100):,.0f}%</td></tr>
                    <tr><td>Minimum Validator Stake:</td><td class='text-end'>{micro_ccd_display(pp.minimum_equity_capital)}</td></tr>
                    <tr><td>Minimum Capital Bound:</td><td class='text-end'>{(pp.capital_bound.value*100):,.0f}%</td></tr>
                    <tr><td>Maximum Leverage:</td><td class='text-end'>{(int(pp.leverage_bound.value.numerator)/int(pp.leverage_bound.value.denominator)):,.0f}</td></tr>
                    </table>
                    """,
                    None,
                )
                self.events_list.append(new_event)

            self.classifier = TransactionClassifier.Chain

            self.dct = dct

    def _prepare(self, transaction: CCD_BlockItemSummary):
        if transaction.type.type == TransactionClass.AccountTransaction.value:
            self.csv = {
                "timestamp": f"{transaction.block_info.slot_time:%Y-%m-%d %H:%M:%S}",
                "transaction_type": transaction.type.type,
                "memo": self.dct["memo"],
                "from_account": transaction.account_transaction.sender,
                "to_account": self.to_account,
                "amount": (
                    f"{(int(self.amount) / 1_000_000):.6f}" if self.amount else ""
                ),
                "amount_currency": "CCD",
                "fee_amount": f"{(int(self.transaction.account_transaction.cost) / 1_000_000):.6f}",
                "fee_currency": "CCD",
                "transaction_hash": self.transaction.hash,
                "block_height": transaction.block_info.height,
                "block_hash": self.transaction.block_info.hash,
            }
        else:
            self.csv = {
                "timestamp": f"{transaction.block_info.slot_time:%Y-%m-%d %H:%M:%S}",
                "transaction_type": transaction.type.type,
                "memo": self.dct["memo"],
                "from_account": "",
                "to_account": "",
                "amount": "",
                "amount_currency": "CCD",
                "fee_amount": "",
                "fee_currency": "CCD",
                "transaction_hash": self.transaction.hash,
                "block_height": transaction.block_info.height,
                "block_hash": self.transaction.block_info.hash,
            }
        return self
