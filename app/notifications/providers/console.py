import logging
from app.notifications.providers.base import NotificationProvider
from app.notifications.models import Notification

logger = logging.getLogger(__name__)


class ConsoleEmailProvider(NotificationProvider):
    def send(self, notification: Notification) -> bool:
        """Simulates sending an email by printing to the console/logger."""
        output = f"""
==================================================
EMAIL SIMULATION
To: User ID {notification.recipient_user_id}
Priority: {notification.priority.value}
Type: {notification.type.value}
--------------------------------------------------
Subject: {notification.title}

{notification.message}
==================================================
"""
        logger.info(output)
        return True
