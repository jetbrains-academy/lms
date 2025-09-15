from djchoices import C, DjangoChoices

from django.utils.translation import gettext_lazy as _

BASE_THUMBNAIL_WIDTH = 176
BASE_THUMBNAIL_HEIGHT = 246


class GenderTypes(DjangoChoices):
    MALE = C('M', _('Male'))
    FEMALE = C('F', _('Female'))
    OTHER = C('o', _('Other/Prefer Not to Say'))


class ThumbnailSizes(DjangoChoices):
    """
    Base image aspect ratio is `5:7`.
    """
    BASE = C(f'{BASE_THUMBNAIL_WIDTH}x{BASE_THUMBNAIL_HEIGHT}')
    BASE_PRINT = C('250x350')
    SQUARE = C('150x150')
    SQUARE_SMALL = C('60x60')
    # FIXME: replace?
    INTERVIEW_LIST = C('100x100')
    # On center site only
    TEACHER_LIST = C("220x308")


# FIXME: remove after deep refactoring:
#  1. Create service method `assign_role(user)` that must validate role id (it's impossible to use role registry as a source for the UserGroup.role choices')
#  2. Use this method to assign permission roles in the admin. (`auth.registry.role_registry` should be used for the admin form)
#  3. For backward compatibility it's better to change role id type to string
#  (after removing Role from the registry it's impossible to figure out what surrogate key means)
class Roles(DjangoChoices):
    STUDENT = C(1, _('Student'))
    TEACHER = C(2, _('Teacher'))
    CURATOR = C(5, _('Curator'))
    INVITED = C(11, _('Invited User'))
    ALUMNI = C(12, _('Alumni'))


student_permission_roles = {Roles.INVITED, Roles.STUDENT, Roles.ALUMNI}
