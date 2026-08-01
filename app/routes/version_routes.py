"""OpsForge Version Endpoint Route.

Exposes application version and build metadata.
"""

import os
from flask_restx import Namespace, Resource, fields

# Namespace definition
ns = Namespace("version", description="Application version metadata")

version_model = ns.model(
    "VersionInfo",
    {
        "version": fields.String(example="0.1.0"),
        "git_commit": fields.String(example="unknown"),
        "build_date": fields.String(example="unknown"),
    },
)


@ns.route("")
class VersionResource(Resource):
    @ns.doc("get_version", description="Returns application build metadata")
    @ns.marshal_with(version_model, code=200)
    def get(self) -> dict:
        version = "0.1.0"
        try:
            root_dir = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            version_path = os.path.join(root_dir, "VERSION")
            if os.path.exists(version_path):
                with open(version_path, "r") as f:
                    version = f.read().strip()
        except Exception:
            pass

        return {
            "version": version,
            "git_commit": os.getenv("GIT_COMMIT", "unknown"),
            "build_date": os.getenv("BUILD_DATE", "unknown"),
        }
