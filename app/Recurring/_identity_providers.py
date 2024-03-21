from ccdexplorer_fundamentals.GRPCClient import GRPCClient
from ccdexplorer_fundamentals.enums import NET


class Mixin:
    def process_identity_providers(self):
        self.grpcclient: GRPCClient
        self.identity_providers = {"mainnet": {}, "testnet": {}}
        for net in NET:
            tmp = self.grpcclient.get_identity_providers("last_final", net)

            for id in tmp:
                self.identity_providers[net.value][id.identity] = {
                    "ip_identity": id.identity,
                    "ip_description": id.description.name,
                }
