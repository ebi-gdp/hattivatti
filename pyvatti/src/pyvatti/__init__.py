import logging
import pathlib
import tempfile

import httpx

logger = logging.getLogger(__name__)
log_fmt = "%(name)s: %(asctime)s %(levelname)-8s %(message)s"
logging.basicConfig(format=log_fmt, datefmt="%Y-%m-%d %H:%M:%S", level=logging.INFO)

CLIENT = httpx.AsyncClient()
TEMP_DIR = tempfile.mkdtemp()
SHELF_PATH = str(pathlib.Path(TEMP_DIR) / "shelve.dat")
logger.info(f"Created temporary shelf file {SHELF_PATH}")
