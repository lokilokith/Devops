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
    "hostname_ip": fields.String(
        description="Hostname or IP Address", example="10.0.0.5"
    ),
    "protocol": fields.String(description="Protocol", example="tcp"),
    "port": fields.Integer(description="Port", example=5432),
    "environment": fields.String(description="Environment", example="prod"),
    "criticality": fields.String(description="Criticality", example="high"),
    "connection_method": fields.String(description="Connection Method", example="ssh"),
    "owner_id": fields.String(description="Owner User UUID", required=False),
    "created_by": fields.String(description="Creator User UUID", required=False),
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
        "hostname_ip": fields.String(required=False, description="Hostname or IP"),
        "protocol": fields.String(required=False, description="Protocol"),
        "port": fields.Integer(required=False, description="Port"),
        "environment": fields.String(required=False, description="Environment"),
        "criticality": fields.String(required=False, description="Criticality"),
        "connection_method": fields.String(
            required=False, description="Connection Method"
        ),
        "owner_id": fields.String(required=False, description="Owner User UUID"),
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
        "hostname_ip": fields.String(required=False, description="Hostname or IP"),
        "protocol": fields.String(required=False, description="Protocol"),
        "port": fields.Integer(required=False, description="Port"),
        "environment": fields.String(required=False, description="Environment"),
        "criticality": fields.String(required=False, description="Criticality"),
        "connection_method": fields.String(
            required=False, description="Connection Method"
        ),
        "owner_id": fields.String(required=False, description="Owner User UUID"),
    },
)

resource_patch_model = resources_ns.model(
    "ResourcePatch",
    {
        "resource_name": fields.String(description="Resource Name"),
        "description": fields.String(description="Description"),
        "resource_type": fields.String(description="Resource Type", example="database"),
        "status": fields.String(description="Status", example="active"),
        "hostname_ip": fields.String(description="Hostname or IP"),
        "protocol": fields.String(description="Protocol"),
        "port": fields.Integer(description="Port"),
        "environment": fields.String(description="Environment"),
        "criticality": fields.String(description="Criticality"),
        "connection_method": fields.String(description="Connection Method"),
        "owner_id": fields.String(description="Owner User UUID"),
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
