"""API Core Infrastructure."""

# This file previously held a duplicate Flask-RESTX Api instance.
# All namespaces are now centrally registered in app/routes/__init__.py
# to ensure they map to the single CustomApi instance attached to the Flask app.
