import logging

from social_core.backends.gitlab import GitLabOAuth2
from social_core.backends.oauth import BaseOAuth2
from social_core.utils import handle_http_errors

from django.contrib.auth import get_user_model

from .registry import role_registry

logger = logging.getLogger(__name__)

UserModel = get_user_model()


class RBACPermissions:
    """
    Backend uses RBAC model approach allowing to check permissions
    both on model and object level.

    Implementation relies on `UserModel.roles` attribute that must return
    set of available roles for the user.
    """
    def authenticate(self, *args, **kwargs):
        return None

    def has_perm(self, user, perm, obj=None):
        if not user.is_active and not user.is_anonymous:
            return False
        if user.is_anonymous:
            return self._has_perm(user, perm, {role_registry.anonymous_role}, obj)
        elif hasattr(user, 'roles'):
            roles = [role_registry.anonymous_role, role_registry.authenticated_role]
            for role_code in user.roles:
                if role_code not in role_registry:
                    logger.warning(f'Role with a code {role_code} is not '
                                   f'registered but assigned to the user {user}')
                    continue
                role = role_registry[role_code]
                roles.append(role)
            roles.sort(key=lambda r: r.priority)
            return self._has_perm(user, perm, roles, obj)
        return False

    def _has_perm(self, user, perm_name, roles, obj):
        for role in roles:
            if role.permissions.rule_exists(perm_name):
                return role.permissions[perm_name].test(user, obj)
            # Case when using base permission name, e.g.,
            # `.has_perm('update_comment', obj)` and expecting
            # .has_perm('update_own_comment', obj) will be in a call chain
            # if relation exists
            if perm_name in role.relations:
                # Related `Permission.rule` checks only object level
                # permission
                if obj is None:
                    continue
                for rel_perm_name in role.relations[perm_name]:
                    # Don't terminate access check here since less priority
                    # role still could have a permission relation that returns
                    # positive result
                    if self._has_perm(user, rel_perm_name, {role}, obj):
                        return True
        return False

    def has_module_perms(self, user, app_label):
        return self.has_perm(user, app_label)


class RBACModelBackend(RBACPermissions):
    """
    Authenticates against `users.models.User` like
    `django.contrib.auth.backends.ModelBackend`. Uses own implementation of
    permissions verification based on `django-rules` which
    allows to check permissions on object level
    """
    # FIXME: maintain compatibility with `django.contrib.auth.models.User` permissions verification
    # FIXME: Implement the verification of permissions based on django-rules first (could be used as separated backend for permissions verification)
    # FIXME: Then return migrate back to default `User.groups` implementation to support built-in permissions and `get_user_model()` instead of custom user model
    def authenticate(self, request, username=None, password=None, **kwargs):
        # XXX this is fine, since @ is not allowed in usernames.
        field = "email" if "@" in username else "username"
        try:
            user = UserModel.objects.get(**{field: username})
            if user.check_password(password):
                return user
        except UserModel.DoesNotExist:
            # See comment in 'ModelBackend#authenticate'.
            # Run the default password hasher once to reduce the timing
            # difference between an existing and a non-existing user (#20760).
            UserModel().set_password(password)

    def user_can_authenticate(self, user):
        """
        Reject users with is_active=False. Custom user models that don't have
        that attribute are allowed.
        """
        is_active = getattr(user, 'is_active', None)
        return is_active or is_active is None

    def get_user(self, user_id):
        try:
            user = UserModel._default_manager.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None


class GitLabManyTaskOAuth2(GitLabOAuth2):
    name = 'gitlab-manytask'
    API_URL = 'https://gitlab.manytask.org'
    EXTRA_DATA = [
        ('id', 'id'),
        ('expires_in', 'expires'),
        ('refresh_token', 'refresh_token'),
        ('username', 'username'),
    ]
