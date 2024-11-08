[![Publish DockerHub image](https://github.com/ccdexplorer/ccdexplorer-site/actions/workflows/build-push.yml/badge.svg)](https://github.com/ccdexplorer/ccdexplorer-site/actions/workflows/build-push.yml)

# CCDExplorer Site

The using facing property of CCDExplorer. Now completely redone, in shiny dark mode!

The redesign has removed the dependencies on the DB as well as the node. 

The site is built on [FastAPI](https://fastapi.tiangolo.com/), with all data retrieved via the API. 

## Getting Started

### Prerequisites

1. An API Key from [api.ccdexplorer.io](https://api.ccdexplorer.io).

### Install and Run
0. Git clone, make a venv (`python3 -m venv .venv`) and activate it. 
1. Install dependencies (in the venv)
```zsh
pip install -r requirements.txt
```
2. Set ENV variables
Copy the `.env.sample` to `.env` and adjust the MongoDB and GRPC values if needed. These defaults assume MongoDB and a mainnet and testnet node are running on your local machine. 
3. Start FastAPI process
```zsh
uvicorn app.main:app --loop asyncio --host 0.0.0.0 --port 8000
```
4. Open a browser window at [http://localhost:8000](http://localhost:8000).

The following NPM packages are installed:
bootstrap-icons@1.11.3
- bootstrap@5.3.3
- bootstrap5-toggle@5.1.1
- flatpickr@4.6.13
- htmx-ext-class-tools@2.0.1
- htmx-ext-json-enc@2.0.1
- htmx.org@2.0.1
- jquery@3.7.1
- plotly.js-dist@2.34.0
- sass@1.77.8
- sortable-tablesort@3.2.3

## Deployment
A Dockerfile is supplied that builds the project into a Docker image (this is the image that is being used on [CCDExplorer.io](https://ccdexplorer.io)).
