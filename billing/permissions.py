import logging
from django.db.models.base import ModelBase
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, DjangoModelPermissions


logger = logging.getLogger()


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
    """
    Example of usage:

    class CsaEmailsView(ListAPIView):
        serializer_class = CsaEmailsSerializer
        permission_classes = (ListCodenamePermissions,)
        permission_codenames = [
            'qc.view_produsercsa',
            'csa_users_stand.view_standcsauser',
            'prod_api_main.view_prodoptions',
        ]
        method_permission_codenames = {
            'POST': ['board_combiner.add_devcombining'],
        }

    will check for 3 permissions for the user on GET request, and 4 permissions for POST
    """
    message = None

    def has_permission(self, request, view):
        codenames = getattr(view, 'permission_codenames', [])
        method_permission = getattr(view, 'method_permission_codenames', {})
        method_codenames = method_permission.get(request.method, [])

        if missing := {i for i in [*codenames, *method_codenames] if not request.user.has_perm(i)}: # pyright: ignore[reportAttributeAccessIssue]
            logger.warning(
                f"User {request.user.id} denied access to {view.__class__.__name__}." # pyright: ignore[reportAttributeAccessIssue]
                f"Missing permissions: {list(missing)}",
            )
            raise PermissionDenied({
                "detail": "You do not have permission to perform this action.",
                "code": "missing_permissions",
            })
        return True


class PermissionPattern(str):
    pattern = '%(app_label)s.%(model_name)s'

    @staticmethod
    def _get_params(model: ModelBase):
        return {
            'app_label': model._meta.app_label, # pyright: ignore[reportAttributeAccessIssue]
            'model_name': model._meta.model_name, # pyright: ignore[reportAttributeAccessIssue]
        }

    def __new__(cls, value, *args, **kwargs):
        if isinstance(value, ModelBase):
            return cls.pattern % cls._get_params(value)
        raise NotImplementedError(f"Can only be used with ModelBase classes, not {type(value)}")


class View(PermissionPattern):
    pattern = '%(app_label)s.view_%(model_name)s'


class Change(PermissionPattern):
    pattern = '%(app_label)s.change_%(model_name)s'


class Add(PermissionPattern):
    pattern = '%(app_label)s.add_%(model_name)s'


class Delete(PermissionPattern):
    pattern = '%(app_label)s.delete_%(model_name)s'


class Reset(PermissionPattern):
    pattern = '%(app_label)s.reset_%(model_name)s'

