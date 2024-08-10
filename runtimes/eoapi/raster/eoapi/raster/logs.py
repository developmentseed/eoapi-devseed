from logging import config
from typing import Any, Dict


def init_logging(debug: bool = False, loggers: Dict[str, Any] = {}):
    config.dictConfig(
        # https://docs.python.org/3/library/logging.config.html#logging-config-dictschema
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "std": {
                    "format": "[%(asctime)s +0000] [%(process)d] [%(levelname)s] %(name)s: %(message)s",
                }
            },
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "std",
                }
            },
            "loggers": {
                # Root logger config
                "": {"handlers": ["stdout"], "level": "DEBUG" if debug else "INFO"},
                # Customized logger config
                **loggers,
            },
        }
    )
