from flask_restx import fields, Model, reqparse

notification_response_model = Model("Notification", {
    "id": fields.String(description="Notification ID"),
    "recipient_user_id": fields.String(description="Recipient User ID"),
    "title": fields.String(description="Title"),
    "message": fields.String(description="Message"),
    "type": fields.String(description="Notification Type"),
    "status": fields.String(description="Notification Status"),
    "priority": fields.String(description="Notification Priority"),
    "is_read": fields.Boolean(description="Is Read"),
    "created_at": fields.DateTime(description="Creation Timestamp"),
    "read_at": fields.DateTime(description="Read Timestamp"),
    "metadata_payload": fields.Raw(description="Metadata Payload"),
    "delivery_attempts": fields.Integer(description="Delivery Attempts"),
})

notification_list_response_model = Model("NotificationListResponse", {
    "success": fields.Boolean(default=True),
    "data": fields.List(fields.Nested(notification_response_model)),
})

notification_single_response_model = Model("NotificationSingleResponse", {
    "success": fields.Boolean(default=True),
    "data": fields.Nested(notification_response_model),
})

notification_unread_count_model = Model("NotificationUnreadCountResponse", {
    "success": fields.Boolean(default=True),
    "data": fields.Integer(description="Unread Count"),
})

notification_mark_all_response_model = Model("NotificationMarkAllResponse", {
    "success": fields.Boolean(default=True),
    "data": fields.Integer(description="Number of notifications marked as read"),
})

# Parsers for filtering
notification_list_parser = reqparse.RequestParser()
notification_list_parser.add_argument("status", type=str, required=False, location="args")
notification_list_parser.add_argument("type", type=str, required=False, location="args")
notification_list_parser.add_argument("priority", type=str, required=False, location="args")
notification_list_parser.add_argument("is_read", type=str, required=False, location="args")
notification_list_parser.add_argument("recipient", type=str, required=False, location="args")
notification_list_parser.add_argument("created_after", type=str, required=False, location="args")
notification_list_parser.add_argument("created_before", type=str, required=False, location="args")
notification_list_parser.add_argument("limit", type=int, required=False, default=50, location="args")
notification_list_parser.add_argument("offset", type=int, required=False, default=0, location="args")
