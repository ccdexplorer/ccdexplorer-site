import json

class Contract:
    def __init__(self, address:str, raw:str):
        self.address = address
        self.raw = raw.splitlines()
        self.state = {}
        self.contract_name = None
        self.owner = None
        self.module_reference = None
        self.state_size = 0 # in bytes
        self.balance = 0 # in microCCD
        self.parse_raw()

    def parse_raw(self):
        method_found = False
        state_string = ''
        for index, line in enumerate(self.raw):
            if index == 0:
                self.contract_name = line.split(':')[1].strip()
            if index == 1:
                self.owner = line.split(':')[1].strip().strip('\'')
            if index == 2:
                self.module_reference = line.split(':')[1].strip().strip('\'')
            if index == 3:
                self.balance = float(self.raw[3].split(':')[1].strip().split()[0])
            if index == 4:
                self.state_size = line.split(':')[1].strip()
            if index == 5:
                if line == 'No schema type was found for the state.':
                    break
                elif line != 'State:':
                    break

            if index >= 6:
                method_found = line == 'Methods:'
                if not method_found:
                    state_string += line
                else:
                    break

        try:
            self.state = json.loads(state_string)            
        except:
            pass
        
# class Modules:
#     def __init__(self, module_addresses):
#         self.module_addresses = module_addresses
#         # print (self.module_addresses)

class Module:
    def __init__(self, address:str, raw:str):
        self.address = address
        self.raw = raw.splitlines()
        self.methods = []
        self.contracts = {} # keyed on contract address, so {"index": 0, "subindex": 0}
        self.module_name = None
        self.parse_raw()

    def parse_raw(self):
        for index, line in enumerate(self.raw):
            if index == 1:
                self.wasm_version = line.split(':')[1].strip()
            if index == 3:
                if line[0] == '-':
                    self.module_name = line.split('-')[1].strip()
            if index > 3:
                if '-' in line:
                    self.methods.append(line.split('-')[1].strip())

    def __str__(self):

        return f"{self.address} | {self.module_name} | {self.wasm_version=} | {self.methods}"
            