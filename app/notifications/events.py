from blinker import Namespace

notification_signals = Namespace()

# Signal payloads should be a dict:
# {
#     "event": "event_name",
#     "request_id": "...",
#     "workflow_id": "...",
#     "actor_id": "...",
#     "recipient_id": "...",
#     "timestamp": "...",
#     "metadata": {}
# }

access_request_created = notification_signals.signal("access_request_created")
request_approved = notification_signals.signal("request_approved")
request_rejected = notification_signals.signal("request_rejected")
request_cancelled = notification_signals.signal("request_cancelled")
approval_required = notification_signals.signal("approval_required")
workflow_failed = notification_signals.signal("workflow_failed")
role_provisioned = notification_signals.signal("role_provisioned")
audit_alert = notification_signals.signal("audit_alert")
