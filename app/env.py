import os
from dotenv import load_dotenv

load_dotenv()

SITE_URL = os.environ.get("SITE_URL")
API_URL = os.environ.get("API_URL")
CCDEXPLORER_API_KEY = os.environ.get("CCDEXPLORER_API_KEY")
SENTRY_DSN = os.environ.get("SENTRY_DSN")
SENTRY_ENVIRONMENT = os.environ.get("SENTRY_ENVIRONMENT")
environment = {
    "SITE_URL": SITE_URL,
    "CCDEXPLORER_API_KEY": CCDEXPLORER_API_KEY,
    "API_URL": API_URL,
    "SENTRY_ENVIRONMENT": SENTRY_ENVIRONMENT,
    "SENTRY_DSN": SENTRY_DSN,
    "NET": "mainnet",
}
