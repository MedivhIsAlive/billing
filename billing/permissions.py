import logging
from django.db.models.base import ModelBase
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, DjangoModelPermissions


log = logging.getLogger("billing.permissions")


class StrictDjangoModelPermissions(DjangoModelPermissions):
    perms_map = {
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "OPTIONS": [],
        "HEAD": [],
        "POST": ["%(app_label)s.add_%(model_name)s"],
        "PUT": ["%(app_label)s.change_%(model_name)s"],
        "PATCH": ["%(app_label)s.change_%(model_name)s"],
        "DELETE": ["%(app_label)s.delete_%(model_name)s"],
    }


class ListCodenamePermissions(BasePermission):
    message = None

    def has_permission(self, request, view):
        codenames = getattr(view, "permission_codenames", [])
        method_permission = getattr(view, "method_permission_codenames", {})
        method_codenames = method_permission.get(request.method, [])

        if missing := {i for i in [*codenames, *method_codenames] if not request.user.has_perm(i)}:
            log.warning(
                f"User {request.user.id} denied access to {view.__class__.__name__}. "
                f"Missing permissions: {list(missing)}"
            )
            raise PermissionDenied({
                "detail": "You do not have permission to perform this action.",
                "code": "missing_permissions",
            })
        return True


class PermissionPattern(str):
    pattern = "%(app_label)s.%(model_name)s"

    @staticmethod
    def _get_params(model: ModelBase):
        return {
            "app_label": model._meta.app_label,
            "model_name": model._meta.model_name,
        }

    def __new__(cls, value, *args, **kwargs):
        if isinstance(value, ModelBase):
            return cls.pattern % cls._get_params(value)
        raise NotImplementedError(f"Can only be used with ModelBase classes, not {type(value)}")


class View(PermissionPattern):
    pattern = "%(app_label)s.view_%(model_name)s"


class Change(PermissionPattern):
    pattern = "%(app_label)s.change_%(model_name)s"


class Add(PermissionPattern):
    pattern = "%(app_label)s.add_%(model_name)s"


class Delete(PermissionPattern):
    pattern = "%(app_label)s.delete_%(model_name)s"


class Reset(PermissionPattern):
    pattern = "%(app_label)s.reset_%(model_name)s"


__all__ = (
    "StrictDjangoModelPermissions",
    "ListCodenamePermissions",
    "View",
    "Change",
    "Add",
    "Delete",
    "Reset",
)
