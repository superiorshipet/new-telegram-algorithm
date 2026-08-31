import logging
import sys

from pythonjsonlogger.json import JsonFormatter


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Avoid verbose third-party logs that can accidentally include transport data.
    logging.getLogger("telethon.network").setLevel(logging.WARNING)
    logging.getLogger("aiogram.event").setLevel(logging.INFO)
