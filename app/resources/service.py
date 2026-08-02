"""Resources feature service layer."""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

from app.resources.exceptions import (
    DuplicateResourceError,
    ResourceNotFoundError,
    ResourcesRepositoryError,
    ResourcesServiceError,
    ValidationError,
)
from app.resources.models import Resource, ResourceType
from app.resources.repository import ResourcesRepository


class ResourcesService:
    def __init__(self, repository: ResourcesRepository):
        self._repository = repository

    def create_resource(self, data: dict) -> Resource:
        resource_code = data.get("resource_code")
        resource_name = data.get("resource_name")
        description = data.get("description")
        resource_type = data.get("resource_type") or ResourceType.SERVER

        if not resource_code or not resource_name:
            raise ValidationError(
                "Missing required fields: resource_code and resource_name"
            )

        try:
            if self._repository.exists_by_resource_code(resource_code):
                raise DuplicateResourceError(
                    f"Resource code '{resource_code}' is already in use."
                )
            if self._repository.exists_by_resource_name(resource_name):
                raise DuplicateResourceError(
                    f"Resource name '{resource_name}' is already in use."
                )
        except ResourcesRepositoryError as e:
            raise ResourcesServiceError(f"Repository validation failed: {e}") from e

        try:
            resource = Resource(
                resource_code=resource_code,
                resource_name=resource_name,
                description=description,
                resource_type=resource_type,
            )
            return self._repository.create(resource)
        except ResourcesRepositoryError as e:
            raise ResourcesServiceError(f"Failed to create resource: {e}") from e

    def get_resource(self, resource_id: UUID) -> Resource:
        try:
            resource = self._repository.get_by_id(resource_id)
            if not resource:
                raise ResourceNotFoundError(f"Resource {resource_id} not found")
            return resource
        except ResourcesRepositoryError as e:
            if isinstance(e, ResourceNotFoundError):
                raise
            raise ResourcesServiceError(f"Failed to retrieve resource: {e}") from e

    def list_resources(
        self, skip: int = 0, limit: int = 100, search: str = ""
    ) -> tuple[Sequence[Resource], int]:
        try:
            resources = self._repository.list(offset=skip, limit=limit)
            total = self._repository.count()
            return resources, total
        except ResourcesRepositoryError as e:
            raise ResourcesServiceError(f"Failed to list resources: {e}") from e

    def update_resource(self, resource_id: UUID, data: dict) -> Resource:
        resource = self.get_resource(resource_id)

        if "resource_name" in data and data["resource_name"] != resource.resource_name:
            try:
                if self._repository.exists_by_resource_name(data["resource_name"]):
                    raise DuplicateResourceError("Resource name is already in use.")
            except ResourcesRepositoryError as e:
                raise ResourcesServiceError(f"Validation failed: {e}") from e
            resource.resource_name = data["resource_name"]

        if "description" in data:
            resource.description = data["description"]

        if "resource_type" in data:
            resource.resource_type = data["resource_type"]

        if "status" in data:
            resource.status = data["status"]

        try:
            return self._repository.update(resource)
        except ResourcesRepositoryError as e:
            raise ResourcesServiceError(f"Failed to update resource: {e}") from e

    def patch_resource(self, resource_id: UUID, data: dict) -> Resource:
        return self.update_resource(resource_id, data)

    def delete_resource(self, resource_id: UUID) -> bool:
        self.get_resource(resource_id)

        try:
            return self._repository.delete(resource_id)
        except ResourcesRepositoryError as e:
            raise ResourcesServiceError(f"Failed to delete resource: {e}") from e

    def search_resources(self, query: str) -> Sequence[Resource]:
        try:
            return self._repository.search(resource_name=query, limit=100)
        except ResourcesRepositoryError as e:
            raise ResourcesServiceError(f"Failed to search resources: {e}") from e

    def count_resources(self) -> int:
        try:
            return self._repository.count()
        except ResourcesRepositoryError as e:
            raise ResourcesServiceError(f"Failed to count resources: {e}") from e

    def activate_resource(self, resource_id: UUID) -> Resource:
        self.get_resource(resource_id)
        try:
            return self._repository.activate(resource_id)
        except ResourcesRepositoryError as e:
            raise ResourcesServiceError(f"Failed to activate resource: {e}") from e

    def deactivate_resource(self, resource_id: UUID) -> Resource:
        self.get_resource(resource_id)
        try:
            return self._repository.deactivate(resource_id)
        except ResourcesRepositoryError as e:
            raise ResourcesServiceError(f"Failed to deactivate resource: {e}") from e
