"""Identical timestamped console + per-process file logging."""
import logging
from pathlib import Path


def get_logger(name):
    logs = Path(__file__).resolve().parent / "logs"
    logs.mkdir(exist_ok=True)
    logger = logging.getLogger("neurolearn." + name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", datefmt="%H:%M:%S")
    fh = logging.FileHandler(logs / (name + ".log"), encoding="utf-8")
    fh.setFormatter(formatter)
    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger
