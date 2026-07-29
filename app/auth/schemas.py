"""Auth REST API Schemas."""
from flask_restx import Namespace, fields

auth_ns = Namespace("auth", description="Authentication operations")

login_model = auth_ns.model("LoginModel", {
    "username": fields.String(required=True, description="Username or Email", example="admin"),
    "password": fields.String(required=True, description="Password", example="secret123")
})

refresh_model = auth_ns.model("RefreshModel", {
    "refresh_token": fields.String(required=True, description="Refresh Token")
})

token_data_model = auth_ns.model("TokenData", {
    "access_token": fields.String(required=True, description="JWT Access Token"),
    "refresh_token": fields.String(description="JWT Refresh Token (optional)"),
    "token_type": fields.String(required=True, description="Token type, e.g. Bearer", default="Bearer", example="Bearer"),
    "expires_in": fields.Integer(required=True, description="Expiration time in seconds", example=3600)
})

token_response_model = auth_ns.model("TokenResponse", {
    "success": fields.Boolean(default=True),
    "message": fields.String(example="Login successful"),
    "data": fields.Nested(token_data_model)
})

user_me_data_model = auth_ns.model("UserMeData", {
    "id": fields.String(description="User UUID"),
    "username": fields.String(description="Username"),
    "email": fields.String(description="Email"),
    "full_name": fields.String(description="Full Name"),
    "roles": fields.List(fields.String, description="List of assigned roles")
})

user_me_response_model = auth_ns.model("UserMeResponse", {
    "success": fields.Boolean(default=True),
    "message": fields.String(),
    "data": fields.Nested(user_me_data_model)
})
