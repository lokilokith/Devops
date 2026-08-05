"""Policy Engine Decisions."""

import enum


class PolicyDecision(str, enum.Enum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"
