"""OpsForge Repositories Package.

Exports all data access repository interfaces.
"""

from app.repositories.threat_repository import ThreatRepository

__all__ = ["ThreatRepository"]
