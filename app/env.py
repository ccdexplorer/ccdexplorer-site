import os
from dotenv import load_dotenv

load_dotenv()

SITE_URL = os.environ.get("SITE_URL")
API_URL = os.environ.get("API_URL")
CCDEXPLORER_API_KEY = os.environ.get("CCDEXPLORER_API_KEY")

environment = {
    "SITE_URL": SITE_URL,
    "CCDEXPLORER_API_KEY": CCDEXPLORER_API_KEY,
    "API_URL": API_URL,
    "NET": "mainnet",
}
