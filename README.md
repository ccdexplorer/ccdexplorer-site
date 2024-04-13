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
Copy the `.env.sample` to `.env` and adjust the MongoDB and GRPC values if needed. These defaults assume MongoDB and a mainnet and testnet node are running on your local machine. 
2. Start FastAPI process
```zsh
uvicorn app.main:app --loop asyncio --host 0.0.0.0 --port 8000
```
3. Open a browser window at [http://localhost:8000](http://localhost:8000).
4. [CAVEAT]: This site depends heavily on data being present in the expected collections. With an ampty DB, the above runs the frontpage of the site. Still working on a feasible way to deliver a pre-filled test db or script to generate this. 


## Deployment
A Dockerfile is supplied that builds the project into a Docker image (this is the image that is being used on [CCDExplorer.io](https://ccdexplorer.io)).
