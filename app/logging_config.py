import logging
import sys

def setup_logging(level=logging.INFO):
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    if any(handler.name == "payment-api" for handler in root_logger.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.set_name("payment-api")
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )

    root_logger.addHandler(handler)
