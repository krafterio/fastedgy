import json
import logging
import os
import sys

from copy import copy
from enum import Enum

try:
    import click
except ImportError:
    click = None


LOG_FORMAT_TEXT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FORMAT_TEXT_LIGHT = "%(levelprefix)s %(message)s"


class StderrFilter(logging.Filter):
    def filter(self, record):
        return record.levelno >= logging.ERROR


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogOutput(str, Enum):
    CONSOLE = "console"
    FILE = "file"
    BOTH = "both"


class LogFormat(str, Enum):
    TEXT = "text"
    TEXT_LIGHT = "text_light"
    JSON = "json"


class StdoutFilter(logging.Filter):
    def filter(self, record):
        return record.levelno < logging.ERROR


class TextFormatter(logging.Formatter):
    def __init__(self):
        super().__init__(LOG_FORMAT_TEXT)


class TextLightFormatter(logging.Formatter):
    level_colors = {
        logging.DEBUG: lambda text: click.style(text, fg="cyan") if click else text,
        logging.INFO: lambda text: click.style(text, fg="green") if click else text,
        logging.WARNING: lambda text: click.style(text, fg="yellow") if click else text,
        logging.ERROR: lambda text: click.style(text, fg="red") if click else text,
        logging.CRITICAL: lambda text: click.style(text, fg="bright_red") if click else text,
    }

    def __init__(self):
        super().__init__(LOG_FORMAT_TEXT_LIGHT)
        self.use_colors = sys.stdout.isatty() and click is not None

    def format(self, record):
        recordcopy = copy(record)
        levelname = recordcopy.levelname
        separator = " " * (8 - len(levelname))

        if self.use_colors:
            color_func = self.level_colors.get(recordcopy.levelno, lambda x: x)
            levelname = color_func(levelname)

        recordcopy.__dict__["levelprefix"] = f"{levelname}:{separator}"
        return super().format(recordcopy)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record),
            "name": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)


class DatabaseConnectionFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, 'msg'):
            return True

        if isinstance(record.msg, str):
            if record.msg.startswith("Connected to database") or record.msg.startswith("Disconnected from database"):
                return False

            if "postgresql+asyncpg://" in record.msg:
                return False

        return True


def setup_logging(
        level: LogLevel = LogLevel.WARNING,
        output: LogOutput = LogOutput.CONSOLE,
        format: LogFormat | str = LogFormat.TEXT,
        log_file: str | None = None,
):
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.value.upper()))

    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    if format == LogFormat.JSON:
        formatter = JsonFormatter()
    elif format == LogFormat.TEXT:
        formatter = TextFormatter()
    elif format == LogFormat.TEXT_LIGHT:
        formatter = TextLightFormatter()
    else:
        formatter = logging.Formatter(format)

    db_connection_filter = DatabaseConnectionFilter()

    if output in [LogOutput.CONSOLE, LogOutput.BOTH]:
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(logging.DEBUG)
        stdout_handler.addFilter(StdoutFilter())
        stdout_handler.addFilter(db_connection_filter)
        stdout_handler.setFormatter(formatter)

        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.ERROR)
        stderr_handler.addFilter(StderrFilter())
        stderr_handler.setFormatter(formatter)

        root_logger.addHandler(stdout_handler)
        root_logger.addHandler(stderr_handler)

    if output in [LogOutput.FILE, LogOutput.BOTH] and log_file:
        log_dir = os.path.dirname(log_file)
        os.makedirs(log_dir, exist_ok=True)

        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.NOTSET)
        file_handler.addFilter(db_connection_filter)
        root_logger.addHandler(file_handler)
