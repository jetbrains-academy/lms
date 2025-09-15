import pytest

from auth.permissions import perm_registry
from courses.tests.factories import CourseProgramBindingFactory, CourseFactory
from learning.tests.factories import EnrollmentFactory
from users.constants import Roles
from users.models import StudentProfile, UserGroup
from users.permissions import (
    ViewAccountConnectedServiceProvider, ViewOwnAccountConnectedServiceProvider, ViewProfile
)
from users.tests.factories import (
    CuratorFactory, StudentFactory, TeacherFactory, UserFactory
)


@pytest.mark.django_db
def test_delete_student_profile():
    """Revoke student permissions on deleting student profile"""
    student = StudentFactory(groups=[Roles.TEACHER])
    assert StudentProfile.objects.filter(user=student).exists()
    student_profile = StudentProfile.objects.get(user=student)
    assert UserGroup.objects.filter(user=student).count() == 2
    assert UserGroup.objects.filter(user=student, role=Roles.STUDENT).exists()
    student_profile.delete()
    assert not UserGroup.objects.filter(user=student, role=Roles.STUDENT).exists()


@pytest.mark.django_db
def test_view_account_connected_service_provider():
    user = UserFactory()
    teacher = TeacherFactory()
    curator = CuratorFactory()
    permission_name = ViewAccountConnectedServiceProvider.name
    assert ViewAccountConnectedServiceProvider in perm_registry
    assert curator.has_perm(permission_name, user)
    assert curator.has_perm(permission_name, curator)
    assert curator.has_perm(permission_name, teacher)


@pytest.mark.django_db
def test_view_own_account_connected_service_provider():
    user = UserFactory()
    teacher = TeacherFactory()
    curator = CuratorFactory()
    permission_name = ViewOwnAccountConnectedServiceProvider.name
    assert not user.has_perm(permission_name, teacher)
    assert not user.has_perm(permission_name, curator)
    assert user.has_perm(permission_name, user)
    assert teacher.has_perm(permission_name, teacher)
    assert not teacher.has_perm(permission_name, curator)
    assert not teacher.has_perm(permission_name, user)


@pytest.mark.django_db
def test_view_account_connected_service_provider_relation():
    user = UserFactory()
    teacher = TeacherFactory()
    curator = CuratorFactory()
    assert not user.has_perm(ViewAccountConnectedServiceProvider.name, teacher)
    assert not user.has_perm(ViewAccountConnectedServiceProvider.name, curator)
    assert user.has_perm(ViewAccountConnectedServiceProvider.name, user)


@pytest.mark.django_db
def test_view_profile(program_run_cub, program_cub001):
    user = StudentFactory()
    user2 = StudentFactory()
    teacher = TeacherFactory()
    teacher2 = TeacherFactory()
    curator = CuratorFactory()
    course = CourseFactory(teachers=[teacher])
    course2 = CourseFactory(teachers=[teacher2])
    permission_name = ViewProfile.name

    assert user.has_perm(permission_name, user)
    assert not user.has_perm(permission_name, user2)
    assert not user.has_perm(permission_name, teacher)
    assert not user.has_perm(permission_name, curator)

    assert curator.has_perm(permission_name, user)
    assert curator.has_perm(permission_name, teacher)
    assert curator.has_perm(permission_name, curator)

    assert not teacher.has_perm(permission_name, user)
    assert not teacher.has_perm(permission_name, user2)

    EnrollmentFactory(student=user, course=course)
    assert teacher.has_perm(permission_name, user)
    assert not teacher.has_perm(permission_name, user2)
    assert not teacher2.has_perm(permission_name, user)

    EnrollmentFactory(student=user, course=course2)
    assert teacher.has_perm(permission_name, user)
    assert not teacher.has_perm(permission_name, user2)
    assert teacher2.has_perm(permission_name, user)

    EnrollmentFactory(student=user2, course=course)
    assert teacher.has_perm(permission_name, user)
    assert teacher.has_perm(permission_name, user2)
    assert teacher2.has_perm(permission_name, user)

    assert user.has_perm(permission_name, user)
    assert not user.has_perm(permission_name, user2)
    assert not user.has_perm(permission_name, teacher)
    assert not user.has_perm(permission_name, curator)

