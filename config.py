import os


class Config:
    API_ID = int(os.environ.get("API_ID", "24776633"))
    API_HASH = os.environ.get("API_HASH", "57b1f632044b4e718f5dce004a988d69")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "8982103415:AAH5meSpQewu-0nBm-yTk1-BBhLyaaOXjS4")

    # Optional
    LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "-1004456487791"))

    # Maximum processing size in MB
    MAX_FILE_SIZE = int(
        os.environ.get("MAX_FILE_SIZE", "2000")
    )
