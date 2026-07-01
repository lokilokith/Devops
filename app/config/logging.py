"""OpsForge Logging Configuration.

Establishes system-wide console logging for the application-scoped logger.
"""

import logging
import sys


def init_logging(debug: bool = False) -> None:
    """Initializes structured console logging once for the 'opsforge' logger."""
    logger = logging.getLogger("opsforge")
    logger.propagate = False  # Prevent log messages from bubbling up to the root logger

    # Clear any existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    level = logging.DEBUG if debug else logging.INFO
    logger.setLevel(level)

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    logger.addHandler(console_handler)
