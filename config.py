import os


class Config:
    API_ID = int(os.environ.get("API_ID", "0"))
    API_HASH = os.environ.get("API_HASH", "")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

    # Optional
    LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "0"))

    # Maximum processing size in MB
    MAX_FILE_SIZE = int(
        os.environ.get("MAX_FILE_SIZE", "2000")
    )
