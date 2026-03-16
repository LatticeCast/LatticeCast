# util/logger.py

import os
import sys

# Log levels
DEBUG = 10
INFO = 20
WARN = 30
ERROR = 40

_level = INFO
if os.getenv("DEBUG_MODE", "0") == "1":
    _level = DEBUG


def set_level(level: int):
    global _level
    _level = level


def _log(level_name: str, level: int, *args):
    if level < _level:
        return
    output = " ".join(str(arg) for arg in args)
    output = output.replace("\n", "\\n")
    print(f"[{level_name}] {output}")
    sys.stdout.flush()


def debug(*args):
    _log("DEBUG", DEBUG, *args)


def info(*args):
    _log("INFO", INFO, *args)


def warn(*args):
    _log("WARN", WARN, *args)


def error(*args):
    _log("ERROR", ERROR, *args)
