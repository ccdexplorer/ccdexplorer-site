[![Publish DockerHub image](https://github.com/ccdexplorer/ccdexplorer-site/actions/workflows/build-push.yml/badge.svg)](https://github.com/ccdexplorer/ccdexplorer-site/actions/workflows/build-push.yml)

# CCDExplorer Site

The site. Oldest codebase, and it shows. 

The site is built on [FastAPI](https://fastapi.tiangolo.com/), with data stored in a [MongoDB](https://www.mongodb.com/) replicaset with 3 members for data redundancy. Data is fetched from 2 sets of Concordium nodes (2 for mainnet, 2 for testnet), using its [GRPC interface](http://developer.concordium.software/concordium-grpc-api/). It retrieves data using a custom [Python GRPC SDK](https://github.com/ccdexplorer/ccdefundamentals/?tab=readme-ov-file#grpcclient). 

## Getting Started

### Prerequisites

1. MongoDB install (you will need to know the Mongo URI and place thata in an ENV)
2. Concordium Nodes for mainnet and testnet (you will need to know the IP and ports for both mainnet and testnet)

### Install and Run
0. Git clone, make a venv (`python3 -m venv .venv`) and activate it. 
1. Install dependencies (in the venv)
```zsh
pip install -r requirements.txt
```
3. Set ENV variables
```
NOTIFIER_API_TOKEN (API token for notifier bot)
API_TOKEN (API token for actual bot)
FASTMAIL_TOKEN (I use Fastmail to send email, leave blank, won't send email)
MONGO_URI (MongoDB URI)
ADMIN_CHAT_ID (Telegram admin chat ID)
MAILTO_LINK (I use Fastmail to send email, leave blank, won't send email)
MAILTO_USER (I use Fastmail to send email, leave blank, won't send email)
GRPC_MAINNET (A list of dicts with GPRC hosts) (Example: [{"host": "localhost", "port": 20000}, {"host": "my.validator.com", "port": 20000}])
GRPC_TESTNET (Same as GPRC_MAINNET)
```
2. Start FastAPI process
```zsh
uvicorn app.main:app --host 0.0.0.0 --port 80
```
3. Open a browser window at [http://localhost:8000](http://localhost:8000).
4. [CAVEAT]: This has not been tested to work flawlessly if the DB doesn't exist, if the correct collections aren't present, if the collections are empty, if the GRPC server isn't present, etc. It works on my machine, but your milage may vary. Happy to make changes to make this work better...


## Deployment
A Dockerfile is supplied that builds the project into a Docker image (this is the image that is being used on [CCDExplorer.io](https://ccdexplorer.io)).
