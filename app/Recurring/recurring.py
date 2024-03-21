from app.Recurring.bakers_nodes_updates import Mixin as baker_nodes

from app.Recurring._identity_providers import Mixin as _identity_providers

from ccdexplorer_fundamentals.enums import NET
from ccdexplorer_fundamentals.ccdscan import CCDScan
from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.mongodb import MongoDB, MongoMotor


class Recurring(
    baker_nodes,
    _identity_providers,
):
    def __init__(self, ccdscan, mongodb, motormongo, grpcclient):
        self.ccdscan: CCDScan = ccdscan
        self.mongodb: MongoDB = mongodb
        self.motormongo: MongoMotor = motormongo
        self.grpcclient: GRPCClient = grpcclient

        self.last_seen_finalized_height = {
            NET.MAINNET: 0,
            NET.TESTNET: 0,
        }

        self.df_accounts = None
        self.baker_nodes_by_baker_id = {}
        self.baker_nodes_by_account_id = {}
        self.non_baker_nodes_by_node_id = {}
        self.non_reporting_bakers_by_baker_id = {}

        self.list_to_sort = []
        self.sorted_nodes = []
        self.election_info = {}
        self.transfer_memos = {}
        self.refresh_Recurring()

    def typer(self):
        return self.ccdscan, self.client

    def refresh_Recurring(self):
        # self.get_memos_from_indices()
        self.df_all_exchange_transactions = None
        self.process_identity_providers()
        self.refresh_nodes_from_collection()
        # self.payday_orchestrator()
