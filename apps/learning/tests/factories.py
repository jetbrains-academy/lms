import datetime

import factory
from django.conf import settings
from django.utils import timezone

from core.tests.factories import LocationFactory
from courses.models import CourseProgramBinding, StudentGroupTypes
from courses.tests.factories import *
from courses.tests.factories import CourseProgramBindingFactory
from learning.models import (
    AssignmentComment, AssignmentNotification, AssignmentSubmissionTypes,
    CourseNewsNotification, Enrollment, Event,
    Invitation, StudentAssignment, StudentGroup, StudentGroupAssignee
)
from learning.services import StudentGroupService
from learning.services.enrollment_service import recreate_assignments_for_student
from learning.services.personal_assignment_service import (
    create_assignment_comment, create_assignment_solution
)
from users.models import StudentTypes
from users.tests.factories import StudentFactory, StudentProfileFactory, UserFactory

__all__ = ('StudentGroupFactory', 'StudentGroupAssigneeFactory',
           'StudentAssignmentFactory', 'AssignmentCommentFactory',
           'EnrollmentFactory', 'InvitationFactory',
           'AssignmentNotificationFactory',
           'CourseNewsNotificationFactory', 'EventFactory',
           'StudentAssignment', 'Enrollment',
           'AssignmentComment')


class StudentGroupFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StudentGroup

    type = StudentGroupTypes.MANUAL
    name = factory.Sequence(lambda n: "Group Name %03d" % n)
    course = factory.SubFactory(CourseFactory)


class StudentGroupAssigneeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StudentGroupAssignee

    student_group = factory.SubFactory(StudentGroupFactory)
    assignee = factory.SubFactory(CourseTeacherFactory)


class StudentAssignmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StudentAssignment

    assignment = factory.SubFactory(AssignmentFactory)
    student = factory.SubFactory(StudentFactory)

    @factory.post_generation
    def create_enrollment(self, create, extracted, **kwargs):
        if not create:
            return
        try:
            Enrollment.objects.get(course=self.assignment.course,
                                   student=self.student)
        except Enrollment.DoesNotExist:
            EnrollmentFactory(course=self.assignment.course,
                              student=self.student)


class AssignmentCommentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AssignmentComment

    student_assignment = factory.SubFactory(StudentAssignmentFactory)
    text = factory.Sequence(lambda n: "Test comment %03d" % n)
    author = factory.SubFactory(UserFactory)
    type = AssignmentSubmissionTypes.COMMENT
    attached_file = factory.django.FileField()

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        is_draft = not kwargs.get('is_published', True)
        if kwargs['type'] == AssignmentSubmissionTypes.COMMENT:
            comment = create_assignment_comment(personal_assignment=kwargs['student_assignment'],
                                                is_draft=is_draft,
                                                created_by=kwargs['author'],
                                                message=kwargs['text'],
                                                attachment=kwargs['attached_file'])
        elif kwargs['type'] == AssignmentSubmissionTypes.SOLUTION:
            comment = create_assignment_solution(personal_assignment=kwargs['student_assignment'],
                                                 created_by=kwargs['author'],
                                                 execution_time=kwargs.get('execution_time'),
                                                 message=kwargs['text'],
                                                 attachment=kwargs['attached_file'])
        else:
            raise ValueError()
        # Consider to move valid kwargs to the create_assignment_comment/_solution
        if 'created' in kwargs:
            comment.created = kwargs['created']
            comment.save(update_fields=['created'])
        return comment


class EnrollmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Enrollment

    student = factory.SubFactory(UserFactory)
    student_profile = factory.SubFactory(
        StudentProfileFactory,
        user=factory.SelfAttribute('..student'),
    )
    course = factory.SubFactory(CourseFactory)

    @factory.post_generation
    def course_program_binding(self: Enrollment, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            self.course_program_binding = extracted
            return
        profile_type = self.student_profile.type
        match profile_type:
            case StudentTypes.REGULAR:
                kwargs.setdefault('program', self.student_profile.academic_program_enrollment.program)
            case StudentTypes.INVITED:
                kwargs.setdefault('program', None)
                kwargs.setdefault('invitation', self.student_profile.invitation)
            case StudentTypes.ALUMNI:
                kwargs.setdefault('is_alumni', True)
        self.course_program_binding = CourseProgramBindingFactory(
            course=self.course,
            **kwargs,
        )

    @factory.post_generation
    def student_group(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            self.student_group = extracted
        else:
            self.student_group = StudentGroupService.resolve(self.course,
                                                             student_profile=self.student_profile)

    @factory.post_generation
    def recreate_assignments(self, create, extracted, **kwargs):
        if not create:
            return
        # Make sure student group is already assigned here
        recreate_assignments_for_student(self)


class InvitationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Invitation

    name = factory.Sequence(lambda n: "Invitation Name %03d" % n)
    semester = factory.SubFactory(SemesterFactory)

    @factory.post_generation
    def courses(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            for course in extracted:
                self.courses.add(course)


class CourseInvitationBindingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CourseProgramBinding
        django_get_or_create = ('course', 'invitation')

    course = factory.SubFactory(CourseFactory)
    program = None
    invitation = factory.SubFactory(InvitationFactory)
    enrollment_end_date = timezone.now() + datetime.timedelta(days=3)
    start_year_filter = None


class AssignmentNotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AssignmentNotification

    user = factory.SubFactory(UserFactory)
    student_assignment = factory.SubFactory(StudentAssignmentFactory)


class CourseNewsNotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CourseNewsNotification

    user = factory.SubFactory(UserFactory)
    course_offering_news = factory.SubFactory(CourseNewsFactory)


class EventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Event

    venue = factory.SubFactory(LocationFactory)
    name = factory.Sequence(lambda n: "Test event %03d" % n)
    description = factory.Sequence(lambda n: "Test event description %03d" % n)
    date = (datetime.datetime.now().replace(tzinfo=timezone.utc)
            + datetime.timedelta(days=3)).date()
    starts_at = datetime.time(hour=13, minute=0)
    ends_at = datetime.time(hour=13, minute=45)
