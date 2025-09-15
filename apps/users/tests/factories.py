import factory
from django.conf import settings

from core.tests.factories import AcademicProgramRunFactory
from users.constants import GenderTypes, Roles
from users.models import (
    StudentProfile, StudentTypes, User, UserGroup, SubmissionForm
)

__all__ = ('User', 'UserFactory', 'CuratorFactory',
           'StudentFactory', 'TeacherFactory',
           'InvitedStudentFactory', 'StudentProfileFactory')

from users.services import assign_role


def add_user_groups(user, groups):
    for role in groups:
        user.add_group(role=role)


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: "testuser%03d" % n)
    gender = factory.Iterator([GenderTypes.MALE, GenderTypes.FEMALE])
    password = "test123foobar@!"
    email = factory.Sequence(lambda n: "user%03d@foobar.net" % n)
    first_name = factory.Sequence(lambda n: "Ivan%03d" % n)
    last_name = factory.Sequence(lambda n: "Petrov%03d" % n)
    time_zone = settings.DEFAULT_TIMEZONE

    @factory.post_generation
    def groups(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            for role in extracted:
                self.add_group(role=role)

    @factory.post_generation
    def raw_password(self, create, extracted, **kwargs):
        if not create:
            return
        raw_password = self.password
        self.set_password(raw_password)
        self.save()
        self.raw_password = raw_password


class UserGroupFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserGroup

    user = factory.SubFactory(UserFactory)
    role = factory.Faker('random_element',
                         elements=[c for c, _ in Roles.choices])


class CuratorFactory(UserFactory):
    is_staff = True
    is_superuser = True

    @factory.post_generation
    def required_groups(self, create, extracted, **kwargs):
        if not create:
            return
        site_id = kwargs.pop("site_id", None)
        self.add_group(role=Roles.CURATOR)


class StudentFactory(UserFactory):
    """
    Student access role will be created by student profile post save signal
    """
    username = factory.Sequence(lambda n: "student%03d" % n)
    email = factory.Sequence(lambda n: "student%03d@test.email" % n)

    @factory.post_generation
    def student_profile(self, create, extracted, **kwargs):
        if not create:
            return
        StudentProfileFactory(user=self, **kwargs)


class InvitedStudentFactory(UserFactory):
    @factory.post_generation
    def student_profile(self, create, extracted, **kwargs):
        if not create:
            return
        StudentProfileFactory(user=self, type=StudentTypes.INVITED, **kwargs)


class TeacherFactory(UserFactory):
    @factory.post_generation
    def required_groups(self, create, extracted, **kwargs):
        if not create:
            return
        site_id = kwargs.pop("site_id", None)
        self.add_group(role=Roles.TEACHER)


class StudentProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StudentProfile
        django_get_or_create = ('user', 'type', 'year_of_admission')

    type = StudentTypes.REGULAR
    user = factory.SubFactory(UserFactory)
    year_of_admission = factory.SelfAttribute('user.date_joined.year')
    academic_program_enrollment = factory.Maybe(
        factory.LazyAttribute(lambda o: o.type == StudentTypes.REGULAR),
        factory.SubFactory(AcademicProgramRunFactory)
    )

    @factory.lazy_attribute
    def invitation(self: StudentProfile):
        from learning.tests.factories import InvitationFactory
        if self.type == StudentTypes.INVITED:
            return InvitationFactory()

    @factory.post_generation
    def add_invitation(self: StudentProfile, create, extracted, **kwargs):
        if self.invitation:
            self.invitations.add(self.invitation)


    @factory.post_generation
    def academic_disciplines(self: StudentProfile, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            for academic_discipline in extracted:
                self.academic_disciplines.add(academic_discipline)

    @factory.post_generation
    def add_permissions(self: StudentProfile, create, extracted, **kwargs):
        if not create:
            return
        # FIXME: use `create_student_profile` service instead by overriding ._create factory method
        permission_role = StudentTypes.to_permission_role(self.type)
        assign_role(account=self.user, role=permission_role)


class SubmissionFormFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SubmissionForm
