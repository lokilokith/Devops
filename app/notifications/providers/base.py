from abc import ABC, abstractmethod

from app.notifications.models import Notification


class NotificationProvider(ABC):
    @abstractmethod
    def send(self, notification: Notification) -> bool:
        """
        Deliver a notification to the recipient.
        Returns True on success, False or raises Exception on failure.
        """
        pass
