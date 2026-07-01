"""OpsForge Logging Configuration.

Establishes system-wide console logging with a uniform format.
"""

import logging
import sys


def init_logging(debug: bool = False) -> None:
    """Initializes structured console logging once for the application."""
    # Clear any existing root handlers to prevent duplicated logs
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    level = logging.DEBUG if debug else logging.INFO

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    logging.root.setLevel(level)
    logging.root.addHandler(console_handler)
