import os
from dotenv import load_dotenv

load_dotenv()

SITE_URL = os.environ.get("SITE_URL")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
DEBUG = os.environ.get("DEBUG", False)
SHOW_DEBUG_LOGS = os.environ.get("SHOW_DEBUG_LOGS", False)
REQUEST_LIMIT = os.environ.get("REQUEST_LIMIT", 20)

environment = {
    "SITE_URL": SITE_URL,
    "NET": "mainnet",
}
