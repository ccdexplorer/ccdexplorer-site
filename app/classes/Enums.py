from enum import Enum


class TimePeriod(Enum):
    LAST_HOUR = "LAST_HOUR"
    LAST24_HOURS = "LAST24_HOURS"
    LAST7_DAYS = "LAST7_DAYS"
    LAST_30_DAYS = "LAST30_DAYS"
    LAST_YEAR = "LAST_YEAR"


class TransactionLimit(Enum):
    _100000 = 100_000
    _500000 = 500_000
    _1000000 = 1_000_000
    _2000000 = 2_000_000
    _5000000 = 5_000_000
    _10000000 = 10_000_000


class AccountSort(Enum):
    AGE_ASC = "AGE_ASC"
    AGE_DESC = "AGE_DESC"
    AMOUNT_ASC = "AMOUNT_ASC"
    AMOUNT_DESC = "AMOUNT_DESC"
    DELEGATED_STAKE_ASC = "DELEGATED_STAKE_ASC"
    DELEGATED_STAKE_DESC = "DELEGATED_STAKE_DESC"
    TRANSACTION_COUNT_ASC = "TRANSACTION_COUNT_ASC"
    TRANSACTION_COUNT_DESC = "TRANSACTION_COUNT_DESC"


class BakerStatus(Enum):
    Inactive = "Previously active as a baker"
    Active = "Active as a baker"
    Not_Reporting = "Active but not reporting to dashboard"


class ExchangePeriod(Enum):
    Last_hour = 1
    Last_day = 24
    Last_week = 24 * 7
    Last_30_days = 24 * 30
    Last_90_days = 24 * 90
    All_time = 24 * 365 * 1000  # 1000 years


class SortKey(Enum):
    # nodeName = "Name"
    total_stake = "Total Stake"
    delegated_stake = "Delegated Stake"
    # total_balance = "Total Balance"
    baker_id = "Baker ID"
    # lottery_power = "Lottery Power"
    # uptime = "Uptime"
    # ping                        = 'Ping'
    # credential_creation_date    = 'Creation Date'
    # client = "Client"
    # finalizer = "Finalizer"
    # peer_count = "Peer Count"


class MongoSortKey(Enum):
    # d30 = "APY 30d Delegators"
    # d90 = "APY 90d Delegators"
    block_commission_rate = "Block Commission"
    tx_commission_rate = "Transaction Commission"
    d180 = "APY 180d Delegators"
    expectation = "Expectation"
    delegated_percentage = "Delegated Percentage"
    # delegated_capital_cap = "Delegated Capital Cap"


class QLSortKey(Enum):
    bakerId = "Baker ID"
    last24_hoursBakerReward = "24h Baker Reward"
    last7_daysBakerReward = "7d Baker Reward"
    last30_daysBakerReward = "30d Baker Reward"
    last24_hoursDelegatorsReward = "24h Delegators Reward"
    last7_daysDelegatorsReward = "7d Delegators Reward"
    last30_daysDelegatorsReward = "30d Delegators Reward"
    last24_hoursTotalReward = "24h Delegators Reward"
    last7_daysTotalReward = "7d Total Reward"
    last30_daysTotalReward = "30d Total Reward"
    stakedAmount = "Staked Amount"
    delegatorCount = "Delegator Count"
    delegatedStake = "Delegated Stake"
    delegationPercentage = "Delegated %"
    totalStake = "Total Stake"
    apy_30_baker = "APY 30d Baker"
    apy_7_baker = "APY 7d Baker"
    apy_30_delegators = "APY 30d Delegators"
    apy_7_delegators = "APY 7d Delegators"
    apy_30_total = "APY 30d Delegators"
    apy_7_total = "APY 7d Delegators"


class PoolStatus(Enum):
    open_for_all = "Open for All"
    closed_for_new = "Closed for New"
    closed_for_all = "Closed for All"


class QLPoolStatus(Enum):
    OPEN_FOR_ALL = "Open for All"
    CLOSED_FOR_NEW = "Closed for New"
    CLOSED_FOR_ALL = "Closed for All"


class Direction(Enum):
    ascending = "↑"
    descending = "↓"


class TransactionClass(Enum):
    AccountTransaction = "accountTransaction"
    CredentialDeploymentTransaction = "credentialDeploymentTransaction"
    UpdateTransaction = "updateTransaction"
