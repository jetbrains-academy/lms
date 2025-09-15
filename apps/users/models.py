import logging
import os
import uuid
from random import choice
from string import ascii_lowercase, digits
from typing import List, Optional

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser, PermissionsMixin, _user_has_perm
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.encoding import force_bytes, smart_str
from django.utils.functional import cached_property
from django.utils.text import normalize_newlines
from django.utils.translation import gettext_lazy as _
from djchoices import C, DjangoChoices
from model_utils import FieldTracker
from model_utils.fields import AutoLastModifiedField, MonitorField
from model_utils.models import TimeStampedModel
from sorl.thumbnail import ImageField
from taggit.models import TagBase

from api.services import generate_hash
from api.settings import DIGEST_MAX_LENGTH
from auth.permissions import perm_registry
from core.db.fields import TimeZoneField
from core.models import TimestampedModel, AcademicProgramRun
from core.timezone import TimezoneAwareMixin
from core.timezone.constants import DATETIME_FORMAT_RU
from core.urls import reverse
from core.utils import (
    instance_memoize, ru_en_mapping
)
from learning.managers import EnrollmentQuerySet
from learning.settings import StudentStatuses
from notifications.base_models import EmailAddressSuspension
from study_programs.models import StudyProgram, AcademicDiscipline
from users.constants import GenderTypes
from users.constants import Roles
from users.constants import Roles as UserRoles
from users.thumbnails import UserThumbnailMixin
from .managers import CustomUserManager

logger = logging.getLogger(__name__)

# Telegram username may only contain alphanumeric characters or
# single underscores. Should begin only with letter and end with alphanumeric.
TELEGRAM_REGEX = "^(?!.*__.*)[a-z A-Z]\w{3,30}[a-zA-Z0-9]$"
TELEGRAM_USERNAME_VALIDATOR = RegexValidator(regex=TELEGRAM_REGEX)

# Github username may only contain alphanumeric characters or
# single hyphens, and cannot begin or end with a hyphen
GITHUB_LOGIN_VALIDATOR = RegexValidator(regex="^[a-zA-Z0-9](-?[a-zA-Z0-9])*$")


class LearningPermissionsMixin:
    @property
    def is_curator(self):
        return self.is_superuser and self.is_staff

    @property
    def is_student(self):
        return UserRoles.STUDENT in self.roles or UserRoles.INVITED in self.roles

    # FIXME: inline
    @property
    def is_active_student(self):
        return self.is_student and not StudentStatuses.is_inactive(self.status)

    @property
    def is_teacher(self):
        return UserRoles.TEACHER in self.roles

    def get_student_profile(self, **kwargs):
        return None


class Country(models.Model):
    code = models.CharField(
        _("ISO 3166-1 A-3 country code"),
        max_length=3,
        unique=True,
    )
    name = models.CharField(_('Country name'))

    class Meta:
        ordering = ["name"]
        verbose_name = _("Country")
        verbose_name_plural = _("Countries")

    def __str__(self):
        return self.name


class City(models.Model):
    name = models.CharField(_("City name"), max_length=255)
    country = models.ForeignKey(
        Country,
        verbose_name=_('Country'),
        on_delete=models.PROTECT,
        related_name='cities',
    )

    class Meta:
        ordering = ["name"]
        verbose_name = _("City")
        verbose_name_plural = _("Cities")

    def __str__(self):
        return self.name


class ExtendedAnonymousUser(LearningPermissionsMixin, AnonymousUser):
    roles = set()
    time_zone = None

    def __str__(self):
        return 'ExtendedAnonymousUser'

    def get_enrollment(self, course_id: int) -> Optional["Enrollment"]:
        return None


class Group(models.Model):
    """
    Groups are a generic way of categorizing users to apply some label.
    A user can belong to any number of groups.

    Groups are a convenient way to categorize users to
    apply some label, or extended functionality, to them. For example, you
    could create a group 'Special users', and you could write code that would
    do special things to those users -- such as giving them access to a
    members-only portion of your site, or sending them members-only email
    messages.
    """
    name = models.CharField(_('name'), max_length=150, unique=True)

    class Meta:
        verbose_name = _('group')
        verbose_name_plural = _('groups')

    def __str__(self):
        return self.name

    def natural_key(self):
        return self.name,


def get_current_site():
    return settings.SITE_ID


class UserGroup(models.Model):
    """Maps users to site and groups. Used by users.groups.AccessGroup."""

    user = models.ForeignKey('users.User', verbose_name=_("User"),
                             on_delete=models.CASCADE,
                             related_name="groups",
                             related_query_name="group")
    site = models.ForeignKey('sites.Site', verbose_name=_("Site"),
                             db_index=False,
                             on_delete=models.PROTECT,
                             default=get_current_site)
    role = models.PositiveSmallIntegerField(_("Role"),
                                            choices=Roles.choices)

    class Meta:
        db_table = "users_user_groups"
        constraints = [
            models.UniqueConstraint(fields=('user', 'role', 'site'),
                                    name='unique_user_role_site'),
        ]
        verbose_name = _("Access Group")
        verbose_name_plural = _("Access Groups")

    @property
    def _key(self):
        """
        Convenience function to make eq overrides easier and clearer.
        Arbitrary decision that group is primary, followed by site and then user
        """
        return self.role, self.site_id, self.user_id

    def __eq__(self, other):
        """
        Overriding eq b/c the django impl relies on the primary key which
        requires fetch. Sometimes we just want to compare groups w/o doing
        another fetch.
        """
        # noinspection PyProtectedMember
        return type(self) == type(other) and self._key == other._key

    def __hash__(self):
        return hash(self._key)

    def __str__(self):
        return "[AccessGroup] user: {}  role: {}  site: {}".format(
            self.user_id, self.role, self.site_id)


class StudentProfileAbstract(models.Model):
    # FIXME: remove
    status = models.CharField(
        choices=StudentStatuses.choices,
        verbose_name=_("Status"),
        max_length=15,
        blank=True)

    class Meta:
        abstract = True


def user_photo_upload_to(instance: "User", filename):
    bucket = instance.pk // 1000
    _, ext = os.path.splitext(filename)
    file_name = uuid.uuid4().hex
    return f"profiles/{bucket}/{file_name}{ext}"


class User(TimezoneAwareMixin, LearningPermissionsMixin, StudentProfileAbstract,
           UserThumbnailMixin, EmailAddressSuspension, AbstractBaseUser):
    TIMEZONE_AWARE_FIELD_NAME = "time_zone"

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']
    GENDER_MALE = GenderTypes.MALE
    GENDER_FEMALE = GenderTypes.FEMALE

    username_validator = UnicodeUsernameValidator()

    username = models.CharField(
        _('username'),
        max_length=150,
        unique=True,
        help_text=_('Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.'),
        validators=[username_validator],
        error_messages={
            'unique': _("A user with that username already exists."),
        },
    )
    first_name = models.CharField(_('first name'), max_length=30)
    last_name = models.CharField(_('last name'), max_length=150)
    email = models.EmailField(_('email address'), unique=True)
    is_staff = models.BooleanField(
        _('staff status'),
        default=False,
        help_text=_('Designates whether the user can log into this admin site.'),
    )
    is_active = models.BooleanField(
        _('active'),
        default=True,
        help_text=_(
            'Designates whether this user should be treated as active. '
            'Unselect this instead of deleting accounts.'
        ),
    )
    is_superuser = models.BooleanField(
        _('superuser status'),
        default=False,
        help_text=_(
            'Designates that this user has all permissions without '
            'explicitly assigning them.'
        ),
    )
    gender = models.CharField(_("Gender"), max_length=1,
                              choices=GenderTypes.choices)
    phone = models.CharField(
        _("Phone"),
        max_length=40,
        blank=True)
    birth_date = models.DateField(_("Date of Birth"), blank=True, null=True)
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)
    modified = AutoLastModifiedField(_('modified'))
    photo = ImageField(
        _("CSCUser|photo"),
        upload_to=user_photo_upload_to,
        blank=True)
    cropbox_data = models.JSONField(
        blank=True,
        null=True
    )
    time_zone = TimeZoneField(_("Time Zone"), null=True)
    bio = models.TextField(
        _("Note"),
        help_text=_("LaTeX+Markdown is enabled"),
        blank=True)
    github_login = models.CharField(
        _("Github Login"),
        max_length=80,
        validators=[GITHUB_LOGIN_VALIDATOR],
        blank=True)
    telegram_username = models.CharField(
        _("Telegram"),
        validators=[TELEGRAM_USERNAME_VALIDATOR],
        max_length=32,
        blank=True)
    codeforces_login = models.CharField(
        _("Codeforces Handle"),
        max_length=80,
        blank=True)
    jetbrains_account = models.EmailField(
        _('JetBrains Account Email'),
        blank=True,
        help_text=_('Email linked to your login across all JetBrains tools. '
                    'If you haven\'t created one before, please register here: '
                    '<a href="https://account.jetbrains.com/login">https://account.jetbrains.com/login</a>')
    )
    cogniterra_user_id = models.PositiveIntegerField(
        _('Cogniterra User ID'),
        blank=True,
        null=True,
        help_text=_('This platform can be used as a verification system in some courses. '
                    'Please create a profile on <a href="https://cogniterra.org/">https://cogniterra.org/</a> '
                    'and provide your User ID. You can find it on your profile page.'),
    )
    linkedin_profile = models.CharField(
        _("LinkedIn Profile"),
        max_length=100,
        blank=True)
    private_contacts = models.TextField(
        _("Contact information"),
        help_text=("{}; {}"
                   .format(_("LaTeX+Markdown is enabled"),
                           _("will be shown only to logged-in users"))),
        blank=True)
    workplace = models.CharField(
        _("Workplace"),
        max_length=200,
        blank=True)
    city = models.ForeignKey(
        City,
        verbose_name=_('City'),
        on_delete=models.SET_NULL,
        related_name='users',
        blank=True,
        null=True,
    )

    updated_at = models.DateTimeField(auto_now=True)

    calendar_key = models.CharField(unique=True, max_length=DIGEST_MAX_LENGTH,
                                    blank=True)

    objects = CustomUserManager()

    class Meta:
        db_table = 'users_user'
        verbose_name = _("CSCUser|user")
        verbose_name_plural = _("CSCUser|users")

    def get_group_permissions(self, obj=None):
        return PermissionsMixin.get_group_permissions(self, obj)

    def get_all_permissions(self, obj=None):
        return PermissionsMixin.get_all_permissions(self, obj)

    def has_perm(self, perm, obj=None):
        is_registered_permission = perm in perm_registry
        # Superuser implicitly has all permissions added by Django and
        # should have access to the Django admin
        if self.is_active and self.is_superuser and not is_registered_permission:
            return True
        # Otherwise we need to check the backends.
        return _user_has_perm(self, perm, obj)

    def has_perms(self, perm_list, obj=None):
        return PermissionsMixin.has_perms(self, perm_list, obj)

    def has_module_perms(self, app_label):
        return PermissionsMixin.has_module_perms(self, app_label)

    def save(self, **kwargs):
        created = self.pk is None
        self.email = self.__class__.objects.normalize_email(self.email)
        if not self.calendar_key:
            self.calendar_key = generate_hash(b'calendar',
                                              force_bytes(self.email))
        super().save(**kwargs)

    def add_group(self, role) -> None:
        self.groups.get_or_create(user=self, role=role)

    def remove_group(self, role):
        self.groups.filter(user=self, role=role).delete()

    @staticmethod
    def generate_random_username(length=30,
                                 chars=ascii_lowercase + digits,
                                 split=4,
                                 delimiter='-',
                                 attempts=10):
        if not attempts:
            return None

        username = ''.join([choice(chars) for _ in range(length)])

        if split:
            username = delimiter.join(
                [username[start:start + split] for start in
                 range(0, len(username), split)])

        try:
            User.objects.get(username=username)
            return User.generate_random_username(
                length=length, chars=chars, split=split, delimiter=delimiter,
                attempts=attempts - 1)
        except User.DoesNotExist:
            return username

    def __str__(self):
        return smart_str(self.get_full_name(True))

    def get_absolute_url(self):
        return reverse('user_detail', args=[self.pk],
                       subdomain=settings.LMS_SUBDOMAIN)

    @instance_memoize
    def get_student_profile(self, **kwargs):
        from users.services import get_student_profile
        return get_student_profile(self, **kwargs)

    def get_student_profile_url(self, subdomain=None):
        return reverse('student_profile', args=[self.pk], subdomain=subdomain)

    def get_update_profile_url(self):
        return reverse('user_update', args=[self.pk],
                       subdomain=settings.LMS_SUBDOMAIN)

    def get_classes_icalendar_url(self):
        # Returns relative path
        return reverse('user_ical_classes', args=[self.pk],
                       subdomain=settings.LMS_SUBDOMAIN)

    def get_assignments_icalendar_url(self):
        return reverse('user_ical_assignments', args=[self.pk],
                       subdomain=settings.LMS_SUBDOMAIN)

    # FIXME: remove
    def teacher_profile_url(self, subdomain=settings.LMS_SUBDOMAIN):
        return reverse('teacher_detail', args=[self.pk],
                       subdomain=subdomain)

    def get_full_name(self, last_name_first=False):
        """
        Returns first name, last name, with a space in between
        or username if not enough data.

        For bibliographic list use `last_name_first=True`
        """
        if last_name_first:
            parts = (self.last_name, self.first_name)
        else:
            parts = (self.first_name, self.last_name)
        full_name = smart_str(" ".join(p for p in parts if p).strip())
        return full_name or self.username

    def get_short_name(self, last_name_first: bool = False) -> str:
        parts = [self.first_name, self.last_name]
        if last_name_first:
            parts.reverse()
        return smart_str(" ".join(parts).strip()) or self.username

    def get_abbreviated_name(self, delimiter=chr(160)):  # non-breaking space
        parts = [self.first_name[:1], self.last_name]
        name = smart_str(f".{delimiter}".join(p for p in parts if p).strip())
        return name or self.username

    def get_abbreviated_short_name(self, last_name_first=True):
        first_letter = self.first_name[:1] + "." if self.first_name else ""
        if last_name_first:
            parts = [self.last_name, first_letter]
        else:
            parts = [first_letter, self.last_name]
        non_breaking_space = chr(160)
        return non_breaking_space.join(parts).strip() or self.username

    def get_abbreviated_name_in_latin(self):
        """
        Returns transliterated user surname + rest initials in lower case.
        Fallback to username. Useful for LDAP accounts.

        Жуков Иван Викторович -> zhukov.i.v
        Иванов Кирилл -> ivanov.k
        """
        parts = [self.last_name, self.first_name[:1]]
        parts = [p.lower() for p in parts if p] or [self.username.lower()]
        # TODO: remove apostrophe
        return ".".join(parts).translate(ru_en_mapping)

    @property
    def photo_data(self):
        if self.photo:
            try:
                return {
                    "url": self.photo.url,
                    "width": self.photo.width,
                    "height": self.photo.height,
                    "cropbox": self.cropbox_data
                }
            except (IOError, OSError):
                pass
        return None

    def get_short_bio(self):
        """Returns only the first paragraph from the bio."""
        normalized_bio = normalize_newlines(self.bio)
        lf = normalized_bio.find("\n")
        return self.bio if lf == -1 else normalized_bio[:lf]

    # FIXME: Sort in priority. Curator role must go before teacher role
    @cached_property
    def roles(self) -> set:
        return {g.role for g in self.groups.all()}

    @instance_memoize
    def get_enrollment(self, course_id: int) -> Optional["Enrollment"]:
        """Returns student enrollment if it exists and not soft deleted"""
        from learning.models import Enrollment
        return (Enrollment.active
                .filter(student=self, course_id=course_id)
                .select_related('student_profile')
                .order_by()
                .first())

    def stats(self, semester, enrollments: Optional[EnrollmentQuerySet] = None):
        """
        Stats for SUCCESSFULLY completed courses and enrollments in
        requested term.
        Additional DB queries may occur:
            * enrollment_set
            * enrollment_set__course (for each enrollment)
            * enrollment_set__course__courseclasses (for each course)
        """
        center_courses = set()
        club_courses = set()
        failed_total = 0
        in_current_term_total = 0
        in_current_term_courses = set()
        in_current_term_passed = 0
        in_current_term_failed = 0
        in_current_term_in_progress = 0
        enrollments = enrollments or self.enrollment_set(manager='active').all()
        for e in enrollments:
            in_current_term = e.course.semester_id == semester.pk
            grading_system = e.course_program_binding.grading_system
            if in_current_term:
                in_current_term_total += 1
                in_current_term_courses.add(e.course.meta_course_id)
            if e.grade >= grading_system.pass_from:
                center_courses.add(e.course.meta_course_id)
                in_current_term_passed += int(in_current_term)
            elif in_current_term:
                if e.grade < grading_system.pass_from:
                    failed_total += 1
                    in_current_term_failed += 1
                else:
                    in_current_term_in_progress += 1
            else:
                failed_total += 1

        return {
            "failed": {"total": failed_total},
            # All the time
            "passed": {
                "total": len(center_courses) + len(club_courses),
                "adjusted": len(center_courses),
                "center_courses": center_courses,
                "club_courses": club_courses,
            },
            # FIXME: collect stats for each term
            "in_term": {
                "total": in_current_term_total,
                "courses": in_current_term_courses,  # center and club courses
                "passed": in_current_term_passed,  # center and club
                "failed": in_current_term_failed,  # center and club
                # FIXME: adusted value, not int
                "in_progress": in_current_term_in_progress,
            }
        }


class StudentTypes(DjangoChoices):
    REGULAR = C('regular', _("Regular Student"))
    INVITED = C('invited', _("Invited Student"))
    ALUMNI = C('alumni', _("Alumni"))

    @classmethod
    def from_permission_role(cls, role):
        if role == Roles.STUDENT:
            return cls.REGULAR
        elif role == Roles.INVITED:
            return cls.INVITED
        elif role == Roles.ALUMNI:
            return cls.ALUMNI

    @classmethod
    def to_permission_role(cls, profile_type):
        if profile_type == cls.REGULAR:
            return Roles.STUDENT
        elif profile_type == cls.INVITED:
            return Roles.INVITED
        elif profile_type == cls.ALUMNI:
            return Roles.ALUMNI


class SubmissionForm(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    academic_program_run = models.ForeignKey(
        AcademicProgramRun,
        verbose_name=_("AcademicProgramRun"),
        related_name="+",
        on_delete=models.CASCADE
    )
    require_student_id = models.BooleanField(
        verbose_name=_('Require Student ID'),
        help_text=_('Show required "Student ID" field in the form'),
        default=True,
    )

    def get_absolute_url(self):
        return reverse('student_addition', kwargs={'formId': self.id})


class AlumniConsent(models.TextChoices):
    NOT_SET = 'not_set', _('Not set')
    DECLINED = 'declined', _('Declined')
    ACCEPTED = 'accepted', _('Accepted')


class StudentProfile(TimeStampedModel):
    type = models.CharField(
        verbose_name=_("Type"),
        max_length=10,
        choices=StudentTypes.choices)
    priority = models.PositiveIntegerField(
        verbose_name=_("Priority"),  # among other user profiles on site
        editable=False
    )
    user = models.ForeignKey(
        User,
        verbose_name=_("Student"),
        related_name="student_profiles",
        on_delete=models.PROTECT, )
    academic_program_enrollment = models.ForeignKey(
        AcademicProgramRun,
        verbose_name=_("ProgramEnrollment"),
        related_name="+",
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )
    student_id = models.CharField(
        verbose_name=_('Student ID'),
        max_length=50,
        blank=True,
    )
    status = models.CharField(
        choices=StudentStatuses.choices,
        verbose_name=_("Status"),
        max_length=15,
        default=StudentStatuses.NORMAL,
    )
    year_of_admission = models.PositiveSmallIntegerField(
        _("Admission year"))
    year_of_graduation = models.PositiveSmallIntegerField(
        _("Graduation year"),
        blank=True,
        null=True,
    )
    university = models.CharField(
        _("University"),
        max_length=255,
        blank=True)
    is_paid_basis = models.BooleanField(
        verbose_name=_("Paid Basis"),
        default=False)
    academic_disciplines = models.ManyToManyField(
        'study_programs.AcademicDiscipline',
        verbose_name=_("Fields of study"),
        blank=True)
    comment = models.TextField(
        _("Comment"),
        blank=True)
    comment_changed_at = MonitorField(
        monitor='comment',
        verbose_name=_("Comment changed"),
        default=None,
        blank=True,
        null=True)
    comment_last_author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Author of last edit"),
        on_delete=models.PROTECT,
        related_name='+',
        blank=True,
        null=True)
    invitation = models.ForeignKey(
        "learning.Invitation",
        verbose_name=_("Invitation"),
        blank=True, null=True,
        related_name="student_profiles",
        on_delete=models.SET_NULL)
    alumni_consent = models.CharField(
        _('Alumni club consent'),
        choices=AlumniConsent.choices,
        default=AlumniConsent.NOT_SET,
    )

    tracker = FieldTracker(fields=['status'])

    class Meta:
        db_table = 'student_profiles'
        verbose_name = _("Student Profile")
        verbose_name_plural = _("Student Profiles")
        constraints = [
            models.UniqueConstraint(
                fields=('user', 'year_of_admission', 'academic_program_enrollment'),
                name='unique_regular_student_per_admission_campaign',
                condition=Q(type=StudentTypes.REGULAR)
            ),
            models.UniqueConstraint(
                fields=('user',),
                name='unique_alumni_profile_per_student',
                condition=Q(type=StudentTypes.ALUMNI)
            ),
        ]

    def save(self, **kwargs):
        from users.services import get_student_profile_priority
        created = self.pk is None
        self.priority = get_student_profile_priority(self)
        self.full_clean()
        update_fields = kwargs.get('update_fields', None)
        if update_fields:
            kwargs['update_fields'] = set(update_fields).union({'priority'})
        super().save(**kwargs)
        if StudentProfile.user.is_cached(self):
            instance_memoize.delete_cache(self.user)

    def clean(self):
        if self.type == StudentTypes.REGULAR and not self.academic_program_enrollment:
            raise ValidationError(_('Academic program enrollment should be set for a regular student'))
        if self.type == StudentTypes.REGULAR and self.invitation:
            raise ValidationError(_('Invitation can\'t be set for a regular student'))
        if self.type == StudentTypes.INVITED and self.academic_program_enrollment:
            raise ValidationError(_('Program can\'t be set for an invited student'))
        if self.type == StudentTypes.ALUMNI and (self.academic_program_enrollment or self.invitation):
            raise ValidationError(_('Program and invitation can\'t be set for an alumni student profile'))

    def __str__(self):
        return f"[StudentProfile] id: {self.pk} name: {self.user.get_full_name()}"

    def get_absolute_url(self, subdomain=None):
        return reverse('user_detail', args=[self.user_id],
                       subdomain=settings.LMS_SUBDOMAIN)

    def get_classes_icalendar_url(self):
        return reverse('user_ical_classes', args=[self.pk],
                       subdomain=settings.LMS_SUBDOMAIN)

    def get_assignments_icalendar_url(self):
        return reverse('user_ical_assignments', args=[self.pk],
                       subdomain=settings.LMS_SUBDOMAIN)

    def get_status_display(self):
        return StudentStatuses.values[self.status]

    @cached_property
    def syllabus(self) -> Optional[List[StudyProgram]]:
        # XXX: Logic for `None` must be reimplemented in
        # `users.services.get_student_profiles` method which injects cache
        # into student profile objects.
        if not self.academic_program_enrollment or self.type == StudentTypes.INVITED:
            return None
        return list(StudyProgram.objects
                    .select_related("academic_discipline")
                    .prefetch_core_courses_groups()
                    .filter(year=self.academic_program_enrollment.start_year))

    @cached_property
    def academic_discipline(self) -> AcademicDiscipline:
        return self.academic_disciplines.first()

    @property
    def is_active(self):
        # FIXME: make sure profile is not expired for invited student? Should be valid only in the term of invitation
        return not StudentStatuses.is_inactive(self.status)

    def get_comment_changed_at_display(self, default=''):
        if self.comment_changed_at:
            return self.comment_changed_at.strftime(DATETIME_FORMAT_RU)
        return default


class StudentStatusLog(TimestampedModel):
    status_changed_at = models.DateField(
        verbose_name=_("Entry Added"),
        default=timezone.now)
    status = models.CharField(
        choices=StudentStatuses.choices,
        verbose_name=_("Status"),
        max_length=15)
    student_profile = models.ForeignKey(
        StudentProfile,
        verbose_name=_("Student"),
        related_name="status_history",
        on_delete=models.CASCADE)
    entry_author = models.ForeignKey(
        User,
        verbose_name=_("Author"),
        on_delete=models.CASCADE)

    class Meta:
        verbose_name_plural = _("Student Status Log")

    def __str__(self):
        return str(self.pk)

    def get_status_display(self):
        if self.status:
            return StudentStatuses.values[self.status]
        # Empty status means studies in progress
        return _("Studying")
