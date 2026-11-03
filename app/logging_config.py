import logging
import sys
from app.telemetry import JsonFormatter

def setup_logging(level=logging.INFO):
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    if any(handler.name == "payment-api" for handler in root_logger.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.set_name("payment-api")
    handler.setFormatter(JsonFormatter())

    root_logger.addHandler(handler)
