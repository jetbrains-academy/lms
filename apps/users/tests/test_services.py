import pytest

from django.core.exceptions import ValidationError
from django.utils import timezone

from core.tests.factories import SiteFactory, AcademicProgramRunFactory
from learning.settings import StudentStatuses
from study_programs.tests.factories import StudyProgramFactory
from users.constants import Roles
from users.models import StudentProfile, StudentTypes, UserGroup
from users.services import (
    StudentStatusTransition, assign_or_revoke_student_role, assign_role,
    create_student_profile, get_student_profile_priority,
    get_student_profiles, maybe_unassign_student_role, unassign_role
)
from users.tests.factories import StudentProfileFactory, UserFactory


@pytest.mark.django_db
def test_assign_role():
    user = UserFactory()
    assign_role(account=user, role=Roles.TEACHER)
    assert user.groups.count() == 1
    assign_role(account=user, role=Roles.TEACHER)
    assert user.groups.count() == 1


@pytest.mark.django_db
def test_unassign_role():
    user = UserFactory()
    assign_role(account=user, role=Roles.TEACHER)
    assert user.groups.count() == 1
    unassign_role(account=user, role=Roles.STUDENT)
    assert user.groups.count() == 1
    unassign_role(account=user, role=Roles.TEACHER)
    assert user.groups.count() == 0


def test_resolve_student_status_transition():
    assert StudentStatusTransition.resolve(StudentStatuses.NORMAL, StudentStatuses.NORMAL) == StudentStatusTransition.NEUTRAL
    assert StudentStatusTransition.resolve(StudentStatuses.NORMAL, StudentStatuses.EXPELLED) == StudentStatusTransition.DEACTIVATION
    assert StudentStatusTransition.resolve(StudentStatuses.EXPELLED, StudentStatuses.NORMAL) == StudentStatusTransition.ACTIVATION


@pytest.mark.django_db
def test_maybe_unassign_student_role():
    student_profile = StudentProfileFactory(type=StudentTypes.REGULAR)
    user = student_profile.user
    user.groups.all().delete()
    assign_role(account=user, role=Roles.STUDENT)
    assert user.groups.count() == 1
    # Not a student role
    with pytest.raises(ValidationError):
        maybe_unassign_student_role(role=Roles.TEACHER, account=user)
    # No other profiles
    maybe_unassign_student_role(role=Roles.STUDENT, account=user)
    assert user.groups.count() == 1
    student_profile.status = StudentStatuses.EXPELLED
    student_profile.save()
    maybe_unassign_student_role(role=Roles.STUDENT, account=user)
    assert user.groups.count() == 0
    # No student profiles of this type
    maybe_unassign_student_role(role=Roles.INVITED, account=user)


@pytest.mark.django_db
def test_assign_or_revoke_student_role():
    user = UserFactory()
    student_profile1 = StudentProfileFactory(
        user=user, type=StudentTypes.REGULAR,
        year_of_admission=2011)
    student_profile2 = StudentProfileFactory(
        user=user, type=StudentTypes.REGULAR,
        year_of_admission=2013)
    UserGroup.objects.all().delete()
    assign_or_revoke_student_role(student_profile=student_profile1,
                                  old_status=StudentStatuses.EXPELLED,
                                  new_status=StudentStatuses.NORMAL)
    assert user.groups.count() == 1
    assert user.groups.get().role == Roles.STUDENT
    assign_or_revoke_student_role(student_profile=student_profile1,
                                  old_status=StudentStatuses.NORMAL,
                                  new_status=StudentStatuses.EXPELLED)
    assert user.groups.count() == 1
    StudentProfile.objects.filter(pk=student_profile1.pk).update(status=StudentStatuses.EXPELLED)
    StudentProfile.objects.filter(pk=student_profile2.pk).update(status=StudentStatuses.EXPELLED)
    assign_or_revoke_student_role(student_profile=student_profile1,
                                  old_status=StudentStatuses.NORMAL,
                                  new_status=StudentStatuses.EXPELLED)
    assert user.groups.count() == 0
    # 1 profile is expelled, 1 is active
    assign_or_revoke_student_role(student_profile=student_profile2,
                                  old_status=StudentStatuses.EXPELLED,
                                  new_status=StudentStatuses.NORMAL)
    StudentProfile.objects.filter(pk=student_profile2.pk).update(status=StudentStatuses.NORMAL)
    assert user.groups.count() == 1
    assert UserGroup.objects.filter(user=user, role=Roles.STUDENT).exists()


@pytest.mark.django_db
def test_get_student_profile_priority():
    student_profile1 = StudentProfileFactory(type=StudentTypes.REGULAR)
    student_profile2 = StudentProfileFactory(type=StudentTypes.INVITED)
    assert get_student_profile_priority(student_profile1) < get_student_profile_priority(student_profile2)
    student_profile3 = StudentProfileFactory(type=StudentTypes.REGULAR,
                                             status=StudentStatuses.EXPELLED)
    assert get_student_profile_priority(student_profile1) < get_student_profile_priority(student_profile3)
    student_profile5 = StudentProfileFactory(type=StudentTypes.REGULAR,
                                             status=StudentStatuses.EXPELLED)
    assert get_student_profile_priority(student_profile2) < get_student_profile_priority(student_profile5)
    student_profile6 = StudentProfileFactory(type=StudentTypes.INVITED,
                                             status=StudentStatuses.EXPELLED)
    assert get_student_profile_priority(student_profile5) == get_student_profile_priority(student_profile6)


@pytest.mark.django_db
def test_create_student_profile(program_run_cub):
    user = UserFactory()
    # Year of curriculum is required for the REGULAR student type
    with pytest.raises(ValidationError):
        create_student_profile(user=user,
                               profile_type=StudentTypes.REGULAR,
                               year_of_admission=2020)
    student_profile = create_student_profile(user=user,
                                             profile_type=StudentTypes.REGULAR,
                                             year_of_admission=2025,
                                             academic_program_enrollment=program_run_cub)
    assert student_profile.user == user
    assert student_profile.type == StudentTypes.REGULAR
    assert student_profile.year_of_admission == 2025
    assert student_profile.academic_program_enrollment.start_year == timezone.now().year
    assert UserGroup.objects.filter(user=user)
    assert UserGroup.objects.filter(user=user).count() == 1
    permission_group = UserGroup.objects.get(user=user)
    assert permission_group.role == StudentTypes.to_permission_role(StudentTypes.REGULAR)
    profile = create_student_profile(user=user,
                                     profile_type=StudentTypes.INVITED,
                                     year_of_admission=2025)
    assert profile.academic_program_enrollment is None


@pytest.mark.django_db
def test_delete_student_profile(program_run_cub):
    """
    Revoke student permissions on site only if no other student profiles of
    the same type are exist after removing profile.
    """
    user = UserFactory()
    student_profile = create_student_profile(user=user,
                                             profile_type=StudentTypes.INVITED,
                                             year_of_admission=2025)
    student_profile1 = create_student_profile(user=user,
                                              profile_type=StudentTypes.REGULAR,
                                              year_of_admission=2025,
                                              academic_program_enrollment=program_run_cub)
    student_profile2 = create_student_profile(user=user,
                                              profile_type=StudentTypes.REGULAR,
                                              year_of_admission=2026,
                                              academic_program_enrollment=program_run_cub)
    assert UserGroup.objects.filter(user=user).count() == 2
    student_profile1.delete()
    assert UserGroup.objects.filter(user=user).count() == 2
    student_profile2.delete()
    assert UserGroup.objects.filter(user=user).count() == 1
    permission_group = UserGroup.objects.get(user=user)
    assert permission_group.role == StudentTypes.to_permission_role(StudentTypes.INVITED)


@pytest.mark.django_db
def test_get_student_profiles(django_assert_num_queries, program_run_nup):
    user = UserFactory()
    student_profile1 = create_student_profile(user=user,
                                              profile_type=StudentTypes.INVITED,
                                              year_of_admission=2025)
    student_profile2 = create_student_profile(user=user,
                                              profile_type=StudentTypes.REGULAR,
                                              year_of_admission=2025,
                                              academic_program_enrollment=program_run_nup)
    student_profiles = get_student_profiles(user=user)
    assert len(student_profiles) == 2
    assert student_profile2.priority < student_profile1.priority
    assert student_profile1 == student_profiles[1]
    assert student_profile2 == student_profiles[0]  # higher priority
    with django_assert_num_queries(3):
        # 1) student profiles 2) empty study programs 3) status history
        student_profiles = get_student_profiles(user=user, fetch_status_history=True)
        for sp in student_profiles:
            assert not sp.status_history.all()
    with django_assert_num_queries(4):
        student_profiles = get_student_profiles(user=user)
        for sp in student_profiles:
            assert not sp.status_history.all()


@pytest.mark.django_db
def test_get_student_profiles_prefetch_syllabus(django_assert_num_queries, program_cub001):
    user = UserFactory()
    program_run_2024 = AcademicProgramRunFactory(program=program_cub001, start_year=2024)
    program_run_2025 = AcademicProgramRunFactory(program=program_cub001, start_year=2025)
    student_profile1 = create_student_profile(user=user,
                                              profile_type=StudentTypes.INVITED,
                                              year_of_admission=2024)
    student_profile2 = create_student_profile(user=user,
                                              profile_type=StudentTypes.REGULAR,
                                              year_of_admission=2025,
                                              academic_program_enrollment=program_run_2025)
    student_profile3 = create_student_profile(user=user,
                                              profile_type=StudentTypes.REGULAR,
                                              year_of_admission=2024,
                                              academic_program_enrollment=program_run_2024)
    study_program_2020_1 = StudyProgramFactory(year=2025)
    study_program_2020_2 = StudyProgramFactory(year=2025)
    study_program_2019 = StudyProgramFactory(year=2024)
    student_profiles = get_student_profiles(user=user)
    assert len(student_profiles) == 3
    assert student_profile2 == student_profiles[0]
    assert 'syllabus' in student_profiles[0].__dict__
    assert student_profiles[0].syllabus == student_profile2.syllabus
    syllabus = student_profiles[0].syllabus
    assert len(syllabus) == 2
    assert study_program_2020_1 in syllabus
    assert study_program_2020_2 in syllabus
    assert 'syllabus' in student_profiles[1].__dict__
    assert student_profiles[1].syllabus == student_profile3.syllabus
    syllabus = student_profiles[1].syllabus
    assert len(syllabus) == 1
    assert study_program_2019 in syllabus
    assert student_profile1 == student_profiles[2]
    assert 'syllabus' in student_profiles[1].__dict__
    assert student_profiles[2].syllabus == student_profile1.syllabus
    assert student_profiles[2].syllabus is None
