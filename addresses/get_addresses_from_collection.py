from ccdexplorer_fundamentals.mongodb import (
    Collections,
    MongoMotor,
)
from ccdexplorer_fundamentals.tooter import Tooter
from app.env import *  # noqa: F403
import asyncio
import pickle

tooter = Tooter()
motormongo = MongoMotor(tooter)


async def main():
    for net in ["mainnet", "testnet"]:
        db_to_use = motormongo.testnet if net == "testnet" else motormongo.mainnet

        get_all_addresses = {
            x["_id"]: x["account_index"]
            for x in await db_to_use[Collections.all_account_addresses]
            .find({})
            .to_list(length=None)
        }

        with open(
            f"addresses/{net}_addresses_to_indexes.pickle", "wb"
        ) as fp:  # Pickling
            pickle.dump(get_all_addresses, fp)
        print(f"{net}: {len(get_all_addresses)} done.")


asyncio.run(main())
