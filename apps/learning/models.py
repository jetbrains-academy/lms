import datetime
import logging
import os
import os.path
from decimal import Decimal
from secrets import token_urlsafe
from typing import Any, Dict, Optional

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.encoding import smart_str
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from djchoices import C, DjangoChoices
from model_utils import FieldTracker
from model_utils.fields import MonitorField
from model_utils.managers import QueryManager
from model_utils.models import TimeStampedModel
from rest_framework.utils.encoders import JSONEncoder

from core.db.fields import ScoreField
from core.db.mixins import DerivableFieldsMixin
from core.db.models import SoftDeletionModel
from core.models import LATEX_MARKDOWN_HTML_ENABLED, Location, TimestampedModel, AcademicProgram, \
    AcademicProgramRun
from core.timezone import TimezoneAwareMixin
from core.urls import reverse
from core.utils import sqids
from courses.constants import AssignmentFormat, AssignmentStatus
from courses.models import Assignment, Course, CourseNews, Semester, StudentGroupTypes, CourseTeacher, \
    CourseProgramBinding
from files.models import ConfigurableStorageFileField
from learning.managers import (
    AssignmentCommentPublishedManager, EnrollmentActiveManager,
    EnrollmentDefaultManager, EventQuerySet,
    StudentAssignmentManager
)
from learning.settings import (
    AssignmentScoreUpdateSource, GradeTypes, GradingSystems, EnrollmentGradeUpdateSource
)
from learning.utils import humanize_duration
from users.models import StudentProfile

logger = logging.getLogger(__name__)


# FIXME: add constraint: 1 system group per course
class StudentGroup(TimeStampedModel):
    type = models.CharField(
        verbose_name=_("Group Type"),
        max_length=100,
        choices=StudentGroupTypes.choices,
        default=StudentGroupTypes.PROGRAM)
    name = models.CharField(
        verbose_name=_("Name"),
        max_length=255)
    course = models.ForeignKey(
        Course,
        verbose_name=_("Course offering"),
        related_name="student_groups",
        on_delete=models.CASCADE)
    enrollment_key = models.CharField(
        verbose_name=_("Enrollment key"),
        max_length=128,
        blank=True)
    program = models.ForeignKey(
        AcademicProgram,
        verbose_name=_('Program'),
        related_name='+',  # Disable backwards relation
        on_delete=models.PROTECT,
        blank=True,
        null=True)
    program_run = models.ForeignKey(
        AcademicProgramRun,
        verbose_name=_('Program run'),
        related_name='+',  # Disable backwards relation
        on_delete=models.PROTECT,
        blank=True,
        null=True)

    class Meta:
        verbose_name = _("Student Group")
        verbose_name_plural = _("Student Groups")

    def __str__(self):
        return self.name

    def save(self, **kwargs):
        created = self.pk is None
        if created and not self.enrollment_key:
            self.enrollment_key = token_urlsafe(18)  # 24 chars in base64
        self.full_clean()  # enforce validation on .get_or_create() calls
        super().save(**kwargs)

    def clean(self):
        if self.type == StudentGroupTypes.PROGRAM and not self.program_id:
            msg = _('Program is not specified for the `program` group type')
            raise ValidationError(msg, code='program')
        elif self.type == StudentGroupTypes.PROGRAM_RUN and not self.program_run_id:
            msg = _('Program run is not specified for the `program_run` group type')
            raise ValidationError(msg, code='program_run')
        mutually_exclusive = ['program_id', 'program_run_id']
        if sum(getattr(self, field_name, None) is not None for field_name in mutually_exclusive) > 1:
            msg = _(f"Fields {mutually_exclusive} are mutually exclusive")
            raise ValidationError(msg, code='malformed')
        if self.course_id and self.name:
            the_same_name = (StudentGroup.objects
                             .exclude(pk=self.pk)
                             .filter(name__iexact=self.name,
                                     program_id=self.program_id,
                                     program_run_id=self.program_run_id,
                                     course_id=self.course_id))
            if the_same_name.exists():
                msg = _("A student group with the same name already exists in the course")
                raise ValidationError(msg, code='unique')

    def get_absolute_url(self):
        return reverse("teaching:student_groups:detail", kwargs={
            "pk": self.pk,
            **self.course.url_kwargs
        })

    def get_update_url(self):
        return reverse("teaching:student_groups:update", kwargs={
            "pk": self.pk,
            **self.course.url_kwargs
        })

    def get_delete_url(self):
        return reverse("teaching:student_groups:delete", kwargs={
            "pk": self.pk,
            **self.course.url_kwargs
        })

    def get_name(self) -> str:
        return self.name


class StudentGroupAssignee(models.Model):
    """
    This model helps to assign teachers who are responsible for the group
    of students during the whole course. For a particular student group
    list of responsible teachers could be overridden on Assignment level.
    """
    student_group = models.ForeignKey(
        StudentGroup,
        verbose_name=_("Student Group"),
        related_name="student_group_assignees",
        on_delete=models.CASCADE)
    assignee = models.ForeignKey(
        'courses.CourseTeacher',
        verbose_name=_("Assignee"),
        on_delete=models.CASCADE)
    assignment = models.ForeignKey(
        'courses.Assignment',
        verbose_name=_("Assignment"),
        blank=True, null=True,
        on_delete=models.CASCADE)

    class Meta:
        verbose_name = _("Student Group Assignee")
        verbose_name_plural = _("Student Group Assignees")
        constraints = [
            models.UniqueConstraint(fields=['student_group', 'assignee'],
                                    condition=Q(assignment__isnull=True),
                                    name='unique_assignee_per_student_group'),
            models.UniqueConstraint(fields=['student_group', 'assignee', 'assignment'],
                                    condition=Q(assignment__isnull=False),
                                    name='unique_assignee_per_student_group_per_assignment'),
        ]

    def __str__(self):
        return "[StudentGroupAssignee] group: {} user: {} assignment: {}".format(
            self.student_group, self.assignee, self.assignment)

    def clean(self):
        if (self.assignee_id and self.student_group_id and
            self.assignee.course_id != self.student_group.course_id):
            raise ValidationError(_('User is not a course teacher of the selected student group'))
        if (self.assignment_id and self.student_group_id and
            self.assignment.course_id != self.student_group.course_id):
            msg = _('Assignment was not found among the course assignments for the selected student group.')
            raise ValidationError(msg)


class StudentGroupTeacherBucket(models.Model):
    """
        The StudentGroupTeacherBucket allows you to select a list of teachers
         to be appointed to students HWs in the selected student groups.
        Buckets with same assignment must not overlap by student_groups,
         but teachers can overlap.
        At best, the student_groups union in all assignment buckets should consist of
         all student groups that have access to that assignment.
    """
    assignment = models.ForeignKey(
        'courses.Assignment',
        verbose_name=_("Assignment"),
        related_name='buckets',
        on_delete=models.CASCADE)
    groups = models.ManyToManyField(
        StudentGroup,
        related_name='buckets',
        verbose_name=_("Groups"))
    teachers = models.ManyToManyField(
        CourseTeacher,
        related_name='buckets',
        verbose_name=_("Teachers")
    )

    class Meta:
        verbose_name = _("Student groups teachers bucket")
        verbose_name_plural = _("Student groups teachers buckets")


class AssignmentGroup(models.Model):
    """
    Course assignment can be restricted to a subset of student groups
    available in the course. AssignmentGroup model stores these settings.
    """
    assignment = models.ForeignKey(
        'courses.Assignment',
        verbose_name=_("Assignment"),
        on_delete=models.CASCADE)
    # TODO: validate assignment.course_id == group.course_id
    group = models.ForeignKey(
        StudentGroup,
        verbose_name=_("Group"),
        # Protect from deleting the last group of the assignment since it
        # will be interpreted as the assignment is available to all
        # student groups which is not true. Manually resolve this issue.
        on_delete=models.PROTECT)

    class Meta:
        verbose_name = _("Assignment Group")
        verbose_name_plural = _("Assignment Groups")
        constraints = [
            models.UniqueConstraint(fields=('assignment', 'group'),
                                    name='unique_assignment_group'),
        ]


class CourseClassGroup(models.Model):
    course_class = models.ForeignKey(
        'courses.CourseClass',
        verbose_name=_("Course Class"),
        on_delete=models.CASCADE)
    group = models.ForeignKey(
        StudentGroup,
        verbose_name=_("Group"),
        on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('course_class', 'group'),
                                    name='unique_class_student_group'),
        ]


class Enrollment(TimezoneAwareMixin, TimeStampedModel):
    TIMEZONE_AWARE_FIELD_NAME = 'course'

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Student"),
        on_delete=models.CASCADE)
    student_profile = models.ForeignKey(
        StudentProfile,
        verbose_name=_("Student Profile"),
        on_delete=models.CASCADE)
    course = models.ForeignKey(
        Course,
        verbose_name=_("Course offering"),
        on_delete=models.CASCADE)
    course_program_binding = models.ForeignKey(
        CourseProgramBinding,
        on_delete=models.PROTECT,
        null=True,
    )
    grade = models.SmallIntegerField(
        verbose_name=_("Enrollment|grade"),
        choices=GradeTypes.choices,
        default=GradeTypes.NOT_GRADED)
    grade_changed = MonitorField(
        verbose_name=_("Enrollment|grade changed"),
        monitor='grade')
    is_deleted = models.BooleanField(
        _("The student left the course"),
        default=False)
    reason_entry = models.TextField(
        _("Entry reason"),
        blank=True)
    reason_leave = models.TextField(
        _("Leave reason"),
        blank=True)
    student_group = models.ForeignKey(
        StudentGroup,
        verbose_name=_("Student Group"),
        related_name="enrollments",
        on_delete=models.PROTECT,
        blank=True,
        null=True)

    objects = EnrollmentDefaultManager()
    active = EnrollmentActiveManager()

    class Meta:
        unique_together = [('student', 'course')]
        verbose_name = _("Enrollment")
        verbose_name_plural = _("Enrollments")

    def __str__(self):
        return "{0} - {1}".format(smart_str(self.course),
                                  smart_str(self.student.get_full_name()))

    def save(self, *args, **kwargs):
        created = self.pk is None
        super().save(*args, **kwargs)

    def clean(self):
        if self.student_profile_id and self.student_profile.user_id != self.student_id:
            raise ValidationError(_("Student profile does not match selected user"))
        if self.student_group_id and self.student_group.course_id != self.course_id:
            raise ValidationError({"student_group": _("Student group must refer to one of the "
                                                      "student groups of the selected course")})
        if self.course_id != self.course_program_binding.course_id:
            raise ValidationError("Course program binding doesn't match the course")
        if (
            (binding_program_id := self.course_program_binding.program_id)
            and self.student_profile.academic_program_enrollment.program_id != binding_program_id
        ):
            raise ValidationError("Course program binding doesn't match the student's program")
        if (
            (binding_invitation_id := self.course_program_binding.invitation_id)
            and not self.student_profile.invitations.filter(id=binding_invitation_id).exists()
        ):
            raise ValidationError("Student profile doesn't have the invitation from the binding")

    def grade_changed_local(self, tz=None):
        if not tz:
            tz = self.get_timezone()
        return timezone.localtime(self.grade_changed, timezone=tz)

    @property
    def grade_display(self):
        return GradeTypes.get_display_grade(self.course_program_binding.grading_system_num, self.grade)

    @property
    def grade_css_class(self):
        grading_system = self.course_program_binding.grading_system
        if self.grade in (GradeTypes.NOT_GRADED, GradeTypes.RE_CREDIT):
            return ''
        if self.grade >= grading_system.excellent_from:
            res = 'excellent'
        elif self.grade >= grading_system.good_from:
            res = 'good'
        elif self.grade >= grading_system.pass_from:
            res = 'pass'
        else:
            res = 'unsatisfactory'
        if grading_system.value == GradingSystems.BINARY:
            res += ' __binary'
        return res

    @property
    def grade_choices(self):
        return GradeTypes.get_choices_for_grading_system(self.course_program_binding.grading_system_num)


class EnrollmentGradeLog(TimestampedModel):
    grade_changed_at = models.DateTimeField(
        verbose_name=_("Entry Added"),
        default=timezone.now)
    grade = models.SmallIntegerField(
        choices=GradeTypes.choices,
        verbose_name=_("Enrollment|grade"))
    enrollment = models.ForeignKey(
        Enrollment,
        verbose_name=_("Enrollment"),
        related_name="grade_history",
        on_delete=models.CASCADE)
    entry_author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Author"),
        on_delete=models.CASCADE)
    source = models.CharField(
        verbose_name=_("Source"),
        choices=EnrollmentGradeUpdateSource.choices,
        max_length=15)

    class Meta:
        verbose_name_plural = "Grade Change Log"

    def __str__(self):
        return str(self.pk)


class Invitation(TimeStampedModel):
    name = models.CharField(_("Name"), max_length=255)
    token = models.CharField(verbose_name=_("Token"), max_length=128)
    semester = models.ForeignKey(
        "courses.Semester",
        verbose_name=_("Semester"),
        on_delete=models.CASCADE)
    courses = models.ManyToManyField(
        'courses.Course',
        through=CourseProgramBinding,
        verbose_name=_("Courses")
    )

    enrolled_students = models.ManyToManyField(
        StudentProfile,
        verbose_name=_("Enrolled students"),
        related_name="invitations",
        help_text=_("Students who took advantage of the invitation"),
        blank=True
    )

    class Meta:
        verbose_name = _("Invitation")
        verbose_name_plural = _("Invitations")
        constraints = [
            models.UniqueConstraint(fields=('semester', 'name'),
                                    name='unique_name_per_semester'),
        ]

    def __str__(self):
        return f"[Invitation] id: {self.pk} name: {self.name}"

    @transaction.atomic
    def save(self, **kwargs):
        created = self.pk is None
        if created and not self.token:
            self.token = token_urlsafe(48)  # 64 chars in base64
        super().save(**kwargs)

    def get_absolute_url(self):
        return reverse("invitation", kwargs={"token": self.token})


class PersonalAssignmentActivity(models.TextChoices):
    STUDENT_COMMENT = 'sc'
    TEACHER_COMMENT = 'tc'
    SOLUTION = 'ns'


class StudentAssignment(SoftDeletionModel, TimezoneAwareMixin, TimeStampedModel,
                        DerivableFieldsMixin):
    TIMEZONE_AWARE_FIELD_NAME = 'assignment'

    assignment = models.ForeignKey(
        Assignment,
        verbose_name=_("StudentAssignment|assignment"),
        on_delete=models.CASCADE)
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("StudentAssignment|student"),
        on_delete=models.CASCADE)
    status = models.CharField(
        verbose_name=_("StudentAssignment|Status"),
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.NOT_SUBMITTED,
        max_length=13)
    score = ScoreField(
        verbose_name=_("Grade"),
        null=True,
        blank=True)
    # Note: not in use, added for further customisation
    # TODO: rename current ScoreField implementation to PositiveScoreField,
    #  ScoreField should allow to store negative values
    penalty = ScoreField(
        verbose_name=_("Penalty"),
        null=True,
        blank=True,
        editable=False)
    score_changed = MonitorField(
        verbose_name=_("Assignment|grade changed"),
        monitor='score')
    assignee = models.ForeignKey(
        'courses.CourseTeacher',
        verbose_name=_("Assignee"),
        on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name="+",  # Disable backwards relation
    )
    trigger_auto_assign = models.BooleanField(
        null=True,
        help_text='Try to set assignee on first student activity',
        editable=False,
        default=True)
    watchers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Student Assignment Watchers"),
        related_name="+",  # Disable backwards relation
        blank=True,  # Make this field optional in django admin
    )
    execution_time = models.DurationField(
        verbose_name=_("Execution Time"),
        blank=True, null=True,
        editable=False,
        help_text=_("The time spent by the student executing this task"),
    )
    meta = models.JSONField(encoder=JSONEncoder, blank=True, null=True,
                            editable=False)

    objects = StudentAssignmentManager()

    tracker = FieldTracker(fields=['score'])

    derivable_fields = ['execution_time']

    class Meta:
        ordering = ["assignment", "student"]
        verbose_name = _("Personal Assignment")
        verbose_name_plural = _("Personal Assignments")
        unique_together = [['assignment', 'student']]

    def clean(self):
        if self.score and self.score > self.assignment.maximum_score:
            raise ValidationError(_("Grade can't be larger than maximum "
                                    "one ({0})")
                                  .format(self.assignment.maximum_score))

    def __str__(self):
        return "{0} - {1}".format(smart_str(self.assignment),
                                  smart_str(self.student.get_full_name()))

    def _compute_execution_time(self):
        time_spent = (AssignmentComment.objects
                      .filter(type=AssignmentSubmissionTypes.SOLUTION,
                              student_assignment=self)
                      .aggregate(total=Sum('execution_time')))
        execution_time = time_spent['total']  # Could be None
        if self.execution_time != execution_time:
            self.execution_time = execution_time
            return True
        return False

    def get_teacher_url(self):
        return reverse('teaching:student_assignment_detail',
                       kwargs={"pk": self.pk})

    def get_student_url(self):
        return reverse('study:student_assignment_detail',
                       kwargs={"pk": self.pk})

    def has_unread(self):
        from notifications.middleware import get_unread_notifications_cache
        cache = get_unread_notifications_cache()
        return self.pk in cache.assignments

    def has_comments(self, user):
        return any(c.author_id == user.pk for c in
                   self.assignmentcomment_set(manager='published').all())

    # TODO -> @cached_property
    @property
    def stats(self) -> Optional[Dict[str, Any]]:
        if (self.meta is None or not isinstance(self.meta, dict) or
            'stats' not in self.meta):
            return None
        stats = {}
        for key, value in self.meta['stats'].items():
            if key == 'solutions':
                solution_stats = {}
                for k, v in value.items():
                    if k == 'first' or k == 'last':
                        # TODO: use drf serializer since we use JSONEncoder
                        #  from this lib
                        v = datetime.datetime.fromisoformat(v.replace('Z', '+00:00'))
                    solution_stats[k] = v
                if 'last' not in solution_stats:
                    solution_stats['last'] = solution_stats['first']
                value = solution_stats
            stats[key] = value
        return stats

    @property
    def is_submission_received(self):
        stats = self.stats
        try:
            if stats is None or not stats.get('solutions', None):
                return False
            # Backward compatibility: remove after stats recalculation
            if isinstance(stats['solutions'], int):
                return stats['solutions'] > 0
            return stats['solutions'].get('count', 0) > 0
        except ValueError:
            return False

    def is_status_transition_allowed(self, status_new):
        statuses = self.assignment.statuses
        if status_new == AssignmentStatus.NOT_SUBMITTED and self.is_submission_received:
            return False
        return status_new in statuses

    def get_score_display(self) -> str:
        if self.score is not None:
            return str(self.score)
        return "—"

    def get_score_verbose_display(self) -> str:
        return f"{self.get_score_display()}/{self.assignment.maximum_score}"

    @property
    def state_display(self) -> str:
        # TODO: replace hybrid state with detached score_display & status
        if self.score is not None:
            return self.get_score_verbose_display()
        else:
            return AssignmentStatus(self.status).label

    @property
    def status_css_class(self) -> str:
        return {
            AssignmentStatus.NOT_SUBMITTED.value: "not-submitted",
            AssignmentStatus.ON_CHECKING.value: "on-checking",
            AssignmentStatus.NEED_FIXES.value: "need-fixes",
            AssignmentStatus.COMPLETED.value: "completed"
        }.get(self.status, "")

    @property
    def final_score(self) -> Optional[Decimal]:
        """Returns sum of score and penalty points."""
        score: Optional[Decimal] = self.score
        penalty: Optional[Decimal] = self.penalty
        # For `penalty` assignment format we store negative penalty value in a
        # score field which could store only positive values
        if self.assignment.submission_type == AssignmentFormat.PENALTY:
            if self.score is not None:
                score, penalty = Decimal(0), -self.score
            else:
                penalty = None
        if score is None:
            return penalty
        elif penalty is not None:
            return score + penalty
        else:
            return score

    # FIXME: remove? .weighted_final_score must be preferred over this prop
    @property
    def weighted_score(self) -> Optional[Decimal]:
        if self.score is None:
            return None
        return self.assignment.weight * self.score

    @property
    def weighted_final_score(self) -> Optional[Decimal]:
        if self.final_score is None:
            return None
        return self.assignment.weight * self.final_score

    def get_execution_time_display(self):
        return humanize_duration(self.execution_time)


class AssignmentScoreAuditLog(TimestampedModel):
    student_assignment = models.ForeignKey(
        StudentAssignment,
        verbose_name=_("Student Assignment"),
        related_name="score_history",
        on_delete=models.CASCADE)
    changed_by = models.ForeignKey(
        'users.User',
        verbose_name=_("Changed by"),
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    score_old = ScoreField(
        verbose_name=_("Previous Score"),
        null=True,
        blank=True)
    score_new = ScoreField(
        verbose_name=_("New Score"),
        null=True,
        blank=True)
    source = models.CharField(
        verbose_name=_("Source"),
        choices=AssignmentScoreUpdateSource.choices,
        max_length=15)

    class Meta:
        verbose_name_plural = _("Assignment score audit log")


def assignment_comment_attachment_upload_to(self: "AssignmentComment",
                                            filename) -> str:
    sa = self.student_assignment
    semester_slug = sa.assignment.course.semester.slug
    return f'assignments/{semester_slug}/{sa.assignment_id}/user_{sa.student_id}/{filename}'


class AssignmentSubmissionTypes(DjangoChoices):
    COMMENT = C('comment', _("Comment"))
    SOLUTION = C('solution', _("Solution"))


class AssignmentComment(SoftDeletionModel, TimezoneAwareMixin, TimeStampedModel):
    TIMEZONE_AWARE_FIELD_NAME = 'student_assignment'

    student_assignment = models.ForeignKey(
        'StudentAssignment',
        verbose_name=_("AssignmentComment|student_assignment"),
        on_delete=models.CASCADE)
    type = models.CharField(
        verbose_name=_("AssignmentComment|Type"),
        max_length=42,
        choices=AssignmentSubmissionTypes.choices
    )
    execution_time = models.DurationField(
        verbose_name=_("Solution Execution Time"),
        blank=True, null=True,
        help_text=_("The time spent by the student executing this submission"))
    is_published = models.BooleanField(_("Published"), default=True)
    text = models.TextField(
        _("AssignmentComment|text"),
        help_text=_("LaTeX+Markdown is enabled"),
        blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Author"),
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    attached_file = ConfigurableStorageFileField(
        verbose_name=_("Attached File"),
        max_length=200,
        upload_to=assignment_comment_attachment_upload_to,
        blank=True)
    meta = models.JSONField(
        encoder=JSONEncoder,
        blank=True, null=True,
        editable=False)

    tracker = FieldTracker(fields=['is_published'])

    published = AssignmentCommentPublishedManager()

    class Meta:
        ordering = ["created"]
        verbose_name = _("Assignment-comment")
        verbose_name_plural = _("Assignment-comments")

    def __str__(self):
        return ("Comment to {0} by {1}".format(
            smart_str(self.student_assignment.assignment),
            smart_str(self.student_assignment.student.get_full_name())))

    def save(self, **kwargs):
        from learning.services.notification_service import generate_notifications_about_new_submission
        from learning.services.personal_assignment_service import maybe_set_assignee_for_personal_assignment
        created = self.pk is None
        is_published_before = bool(self.tracker.previous('is_published'))
        super().save(**kwargs)
        # FIXME: move this logic to create_assignment_comment/create_assignment_solution
        has_been_published = self.is_published and (created or
                                                    not is_published_before)
        # Send notifications on publishing submission
        if has_been_published:
            maybe_set_assignee_for_personal_assignment(self.pk)
            generate_notifications_about_new_submission(self)

    def created_local(self, tz=None):
        if not tz:
            tz = self.get_timezone()
        return timezone.localtime(self.created, timezone=tz)

    def get_update_url(self):
        return reverse('teaching:student_assignment_comment_edit', kwargs={
            "pk": self.student_assignment_id,
            "comment_pk": self.pk
        })

    @property
    def attached_file_name(self):
        return os.path.basename(self.attached_file.name)

    def get_attachment_download_url(self):
        return reverse("study:download_assignment_comment_attachment", kwargs={
            "sid": sqids.encode([self.pk]),
            "file_name": self.attached_file_name
        })

    @property
    def is_stale_for_edit(self) -> bool:
        # Teacher can edit comment during 10 min period only
        return (now() - self.created).total_seconds() > 600

    def get_execution_time_display(self) -> str:
        td: Optional[datetime.timedelta] = self.execution_time
        if td is None:
            return "-:-"
        mm, _ = divmod(td.seconds, 60)
        hh, mm = divmod(mm, 60)
        s = "%d:%02d" % (hh, mm)
        if td.days:
            # TODO: pluralize, add i18n
            return f"{td.days} д. {s}"
        return s

    def get_author_name(self):
        if not self.author:
            return _('System')
        else:
            return self.author.get_full_name()


def assignment_submission_attachment_upload_to(self: "SubmissionAttachment",
                                               filename) -> str:
    sa = self.submission.student_assignment
    semester_slug = sa.assignment.course.semester.slug
    return f'assignments/{semester_slug}/{sa.assignment_id}/user_{sa.student_id}/{filename}'


class SubmissionAttachment(TimeStampedModel):
    """
    This model could be used for multiple attachments for assignment submission
    but currently stores only ipynb files converted to the html format.
    """
    submission = models.ForeignKey(
        AssignmentComment,
        verbose_name=_("Assignment Submission"),
        related_name='attachments',
        on_delete=models.CASCADE)
    attachment = ConfigurableStorageFileField(
        upload_to=assignment_submission_attachment_upload_to,
        max_length=200)

    class Meta:
        verbose_name = _("Assignment Submission Attachment")
        verbose_name_plural = _("Assignment Submission Attachments")

    def __str__(self):
        return self.file_name

    @property
    def file_name(self):
        return os.path.basename(self.attachment.name)

    @property
    def file_ext(self):
        _, ext = os.path.splitext(self.attachment.name)
        return ext

    def get_download_url(self):
        return reverse("study:download_submission_attachment", kwargs={
            "sid": sqids.encode([self.pk]),
            "file_name": self.file_name
        })


class AssignmentNotification(TimezoneAwareMixin, TimeStampedModel):
    TIMEZONE_AWARE_FIELD_NAME = 'student_assignment'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("User"),
        on_delete=models.CASCADE)
    student_assignment = models.ForeignKey(
        'StudentAssignment',
        verbose_name=_("student_assignment"),
        on_delete=models.CASCADE)
    is_about_passed = models.BooleanField(_("About passed assignment"),
                                          default=False)
    is_about_creation = models.BooleanField(_("About created assignment"),
                                            default=False)
    is_about_deadline = models.BooleanField(_("About change of deadline"),
                                            default=False)
    is_unread = models.BooleanField(_("Unread"),
                                    default=True)
    is_notified = models.BooleanField(_("User is notified"),
                                      default=False)

    objects = models.Manager()
    unread = QueryManager(is_unread=True)

    class Meta:
        ordering = ["-created"]
        verbose_name = _("Assignment notification")
        verbose_name_plural = _("Assignment notifications")

    def clean(self):
        if self.is_about_passed and not self.user.is_teacher:
            raise ValidationError(_("Only teachers can receive notifications "
                                    "of passed assignments"))

    def __str__(self):
        return ("notification for {0} on {1}"
                .format(smart_str(self.user.get_full_name()),
                        smart_str(self.student_assignment)))

    def created_local(self, tz=None):
        if not tz:
            tz = self.get_timezone()
        return timezone.localtime(self.created, timezone=tz)


class CourseNewsNotification(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("User"),
        on_delete=models.CASCADE)
    course_offering_news = models.ForeignKey(
        CourseNews,
        verbose_name=_("Course offering news"),
        on_delete=models.CASCADE)
    is_unread = models.BooleanField(_("Unread"),
                                    default=True)
    is_notified = models.BooleanField(_("User is notified"),
                                      default=False)

    objects = models.Manager()
    unread = QueryManager(is_unread=True)

    class Meta:
        ordering = ["-created"]
        verbose_name = _("Course offering news notification")
        verbose_name_plural = _("Course offering news notifications")

    def __str__(self):
        return ("notification for {0} on {1}"
                .format(smart_str(self.user.get_full_name()),
                        smart_str(self.course_offering_news)))


class Event(TimeStampedModel):
    venue = models.ForeignKey(
        Location,
        verbose_name=_("Venue"),
        null=True, blank=True,
        on_delete=models.PROTECT)
    name = models.CharField(_("Name"), max_length=255)
    description = models.TextField(
        _("Description"),
        blank=True,
        help_text=LATEX_MARKDOWN_HTML_ENABLED)
    date = models.DateField(_("Date"))
    starts_at = models.TimeField(_("Starts at"))
    ends_at = models.TimeField(_("Ends at"))

    objects = EventQuerySet.as_manager()

    class Meta:
        ordering = ("-date", "-starts_at", "name")
        verbose_name = _("Non-course event")
        verbose_name_plural = _("Non-course events")

    def __str__(self):
        return "{}".format(smart_str(self.name))

    def clean(self):
        super().clean()
        # ends_at should be later than starts_at
        if self.starts_at >= self.ends_at:
            raise ValidationError(_("Event should end after it's start"))

    # this is needed to share code between CourseClasses and this model
    @property
    def type(self):
        return "noncourse"

    def get_absolute_url(self):
        return reverse('non_course_event_detail',
                       subdomain=settings.LMS_SUBDOMAIN,
                       args=[self.pk])


def graduate_photo_upload_to(*args, **kwargs):
    # referenced in models
    raise NotImplementedError()
