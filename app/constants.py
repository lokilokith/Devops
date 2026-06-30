"""OpsForge Constants.

Centralizes all system-wide enum values, pagination defaults, and configurations.
"""

THREAT_LEVELS = ["low", "medium", "high", "critical"]
THREAT_STATUSES = ["Open", "Investigating", "Contained", "Closed", "False Positive"]
INDICATOR_TYPES = ["ip", "domain", "hash", "url"]

DEFAULT_PAGE = 1
DEFAULT_LIMIT = 20
