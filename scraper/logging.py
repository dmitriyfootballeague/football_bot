import logging

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s.%(msecs)03d] (%(levelname)s) {%(name)s:%(funcName)s:%(lineno)s}: %(message)s",
    datefmt=DATETIME_FORMAT,
)
logger = logging.getLogger("scraper")
