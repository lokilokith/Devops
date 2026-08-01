"""Resources REST API Schemas."""

from flask_restx import Namespace, fields

resources_ns = Namespace("resources", description="Resources management operations")

resource_base = {
    "resource_code": fields.String(description="Resource Code", example="DB_MAIN"),
    "resource_name": fields.String(
        description="Resource Name", example="Main Database"
    ),
    "description": fields.String(
        description="Description", example="Primary PostgreSQL database"
    ),
    "resource_type": fields.String(description="Resource Type", example="database"),
    "status": fields.String(description="Status", example="active"),
}

resource_model = resources_ns.model(
    "Resource",
    {
        "id": fields.String(
            description="Resource UUID", example="12345678-1234-5678-1234-567812345678"
        ),
        **resource_base,
    },
)

resource_create_model = resources_ns.model(
    "ResourceCreate",
    {
        "resource_code": fields.String(required=True, description="Resource Code"),
        "resource_name": fields.String(required=True, description="Resource Name"),
        "description": fields.String(required=False, description="Description"),
        "resource_type": fields.String(
            required=False, description="Resource Type", example="database"
        ),
    },
)

resource_update_model = resources_ns.model(
    "ResourceUpdate",
    {
        "resource_name": fields.String(required=True, description="Resource Name"),
        "description": fields.String(required=False, description="Description"),
        "resource_type": fields.String(
            required=True, description="Resource Type", example="database"
        ),
        "status": fields.String(required=True, description="Status", example="active"),
    },
)

resource_patch_model = resources_ns.model(
    "ResourcePatch",
    {
        "resource_name": fields.String(description="Resource Name"),
        "description": fields.String(description="Description"),
        "resource_type": fields.String(description="Resource Type", example="database"),
        "status": fields.String(description="Status", example="active"),
    },
)

resource_response_model = resources_ns.model(
    "ResourceResponse",
    {
        "success": fields.Boolean,
        "message": fields.String,
        "data": fields.Nested(resource_model),
        "meta": fields.Raw,
    },
)

resource_list_response_model = resources_ns.model(
    "ResourceListResponse",
    {
        "success": fields.Boolean,
        "message": fields.String,
        "data": fields.List(fields.Nested(resource_model)),
        "meta": fields.Raw,
    },
)
