from djchoices import C, DjangoChoices

from django.db.models.enums import TextChoices
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop

AUTUMN_TERM_START = '1 sep'
SPRING_TERM_START = '2 feb'  # XXX: spring term must be later than 1 jan
SUMMER_TERM_START = '1 jul'


MONDAY_WEEKDAY = 0
SUNDAY_WEEKDAY = 6
WEEKDAY_TITLES = [
    gettext_noop("Monday"),
    gettext_noop("Tuesday"),
    gettext_noop("Wednesday"),
    gettext_noop("Thursday"),
    gettext_noop("Friday"),
    gettext_noop("Saturday"),
    gettext_noop("Sunday"),
]


class SemesterTypes(DjangoChoices):
    """
    Term order values must be consecutive numbers and start from
    the beginning of the year.
    """
    SPRING = C('spring', _("spring"), order=1)
    SUMMER = C('summer', _("summer"), order=2)
    AUTUMN = C('autumn', _("autumn"), order=3)


class ClassTypes(DjangoChoices):
    LECTURE = C('lecture', _("Lecture"))
    SEMINAR = C('seminar', _("Seminar"))


class TeacherRoles(DjangoChoices):
    """
    This enum is used in the CourseTeacher.roles bitfield. Order is matter!
    """
    LECTURER = C('lecturer', _("Lecturer"))
    REVIEWER = C('reviewer', _("Reviewer"))
    SEMINAR = C('seminar', _("Seminarian"))
    SPECTATOR = C('spectator', _("Spectator"))
    ORGANIZER = C('organizer', _("Organizer"))


class MaterialVisibilityTypes(DjangoChoices):
    # Includes students that are able to enroll, but not enrolled
    # and students that are expelled or have failed the course
    PARTICIPANTS = C('participants', _('All Students'))
    # Only active enrolled students
    COURSE_PARTICIPANTS = C('private', _('Course Participants'))


class AssignmentFormat(DjangoChoices):
    ONLINE = C("online", _("Online Submission"))  # file or text on site
    JBA = C("jba", _("JetBrains Academy Course"))
    EXTERNAL = C("external", _("External Service"))
    PENALTY = C("penalty", _("Penalty"))
    NO_SUBMIT = C("other", _("No Submission"))  # on paper, etc


class AssignmentStatus(TextChoices):
    # TODO: describe each status
    NEW = 'new', _("New")  # TODO: remove after integration
    NOT_SUBMITTED = 'not_submitted', _("Not submitted")
    ON_CHECKING = 'on_checking', _("On checking")
    NEED_FIXES = 'need_fixes', _("Need fixes")
    COMPLETED = 'completed', _("Completed")


class AssigneeMode(TextChoices):
    DISABLED = 'off', _('Without a responsible person')
    MANUAL = 'manual', _('Choose from the list')
    STUDENT_GROUP_DEFAULT = 'sg_default', _('Student Group - Default')
    STUDENT_GROUP_CUSTOM = 'sg_custom', _('Student Group - Custom')
    STUDENT_GROUP_BALANCED = 'sg_balance', _('Student Group - Balanced')
