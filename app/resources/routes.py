"""Resources REST API Routes."""

from flask import request
from flask_restx import Resource
from werkzeug.exceptions import Conflict

from app.api.decorators import login_required, requires_permission
from app.api.pagination import DEFAULT_PAGE_SIZE, validate_pagination
from app.api.responses import success_response
from app.extensions import db
from app.resources.exceptions import DuplicateResourceError
from app.resources.repository import ResourcesRepository
from app.resources.schemas import (
    resource_create_model,
    resource_list_response_model,
    resource_patch_model,
    resource_response_model,
    resource_update_model,
    resources_ns,
)
from app.resources.service import ResourcesService
from app.resources.validators import (
    validate_resource_create,
    validate_resource_patch,
    validate_resource_update,
    validate_uuid,
)


def get_service():
    return ResourcesService(ResourcesRepository(db.session))


@resources_ns.route("")
class ResourceCollection(Resource):
    @resources_ns.doc(
        summary="List resources", description="Retrieve a paginated list of resources."
    )
    @resources_ns.marshal_with(resource_list_response_model)
    @login_required
    @requires_permission("resources", "read")
    def get(self):
        skip, limit = validate_pagination(
            request.args.get("skip", 0), request.args.get("limit", DEFAULT_PAGE_SIZE)
        )
        service = get_service()
        resources, total = service.list_resources(skip=skip, limit=limit)
        return success_response(
            data=resources, meta={"total": total, "skip": skip, "limit": limit}
        )

    @resources_ns.doc(summary="Create resource", description="Create a new resource.")
    @resources_ns.expect(resource_create_model)
    @resources_ns.marshal_with(resource_response_model, code=201)
    @login_required
    @requires_permission("resources", "create")
    def post(self):
        data = request.json or {}
        validate_resource_create(data)
        service = get_service()
        try:
            resource = service.create_resource(data)
            return success_response(
                data=resource, message="Resource created successfully", status_code=201
            )
        except DuplicateResourceError as e:
            raise Conflict(str(e))


@resources_ns.route("/<string:resource_id>")
class ResourceResource(Resource):
    @resources_ns.doc(
        summary="Get resource", description="Retrieve a resource by UUID."
    )
    @resources_ns.marshal_with(resource_response_model)
    @login_required
    @requires_permission("resources", "read")
    def get(self, resource_id):
        uid = validate_uuid(resource_id)
        service = get_service()
        resource = service.get_resource(uid)

        return success_response(data=resource)

    @resources_ns.doc(
        summary="Update resource", description="Completely update a resource by UUID."
    )
    @resources_ns.expect(resource_update_model)
    @resources_ns.marshal_with(resource_response_model)
    @login_required
    @requires_permission("resources", "update")
    def put(self, resource_id):
        uid = validate_uuid(resource_id)
        data = request.json or {}
        validate_resource_update(data)
        service = get_service()
        try:
            resource = service.update_resource(uid, data)

            return success_response(
                data=resource, message="Resource updated successfully"
            )
        except DuplicateResourceError as e:
            raise Conflict(str(e))

    @resources_ns.doc(
        summary="Partial update resource",
        description="Partially update a resource by UUID.",
    )
    @resources_ns.expect(resource_patch_model)
    @resources_ns.marshal_with(resource_response_model)
    @login_required
    @requires_permission("resources", "update")
    def patch(self, resource_id):
        uid = validate_uuid(resource_id)
        data = request.json or {}
        validate_resource_patch(data)
        service = get_service()
        try:
            resource = service.patch_resource(uid, data)

            return success_response(
                data=resource, message="Resource updated successfully"
            )
        except DuplicateResourceError as e:
            raise Conflict(str(e))

    @resources_ns.doc(
        summary="Delete resource", description="Delete a resource by UUID."
    )
    @resources_ns.marshal_with(resource_response_model)
    @login_required
    @requires_permission("resources", "delete")
    def delete(self, resource_id):
        uid = validate_uuid(resource_id)
        service = get_service()
        service.get_resource(uid)

        service.delete_resource(uid)
        return success_response(message="Resource deleted successfully")
