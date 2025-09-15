import datetime

import pytest
from bs4 import BeautifulSoup
from django.utils import timezone
from django.utils.encoding import smart_bytes
from django.utils.translation import gettext as _

from core.tests.factories import AcademicProgramRunFactory
from core.timezone import now_local
from core.timezone.constants import DATE_FORMAT_RU
from core.urls import reverse
from courses.models import CourseGroupModes
from courses.tests.factories import AssignmentFactory, CourseFactory, SemesterFactory, CourseProgramBindingFactory, \
    MetaCourseFactory
from learning.models import Enrollment, StudentAssignment, StudentGroup
from learning.permissions import EnrollInCourse, EnrollOrLeavePermissionObject
from learning.services import EnrollmentService, StudentGroupService
from learning.services.enrollment_service import CourseCapacityFull
from learning.settings import StudentStatuses
from learning.tests.factories import CourseInvitationBindingFactory, EnrollmentFactory, StudentGroupFactory
from users.services import get_student_profile
from users.tests.factories import (
    InvitedStudentFactory, StudentFactory, StudentProfileFactory
)


@pytest.mark.django_db
def test_service_enroll(settings, program_cub001, program_run_cub):
    student_profile, student_profile2 = StudentProfileFactory.create_batch(
        2, academic_program_enrollment=program_run_cub
    )
    current_semester = SemesterFactory.create_current()
    course = CourseFactory(semester=current_semester,
                           group_mode=CourseGroupModes.MANUAL)
    CourseProgramBindingFactory(course=course, program=program_cub001)
    student_group = StudentGroupFactory(course=course)
    enrollment = EnrollmentService.enroll(student_profile, course,
                                          student_group=student_group, reason_entry='test enrollment')
    reason_entry = EnrollmentService._format_reason_record('test enrollment', course)
    assert enrollment.reason_entry == reason_entry
    assert not enrollment.is_deleted
    assert enrollment.student_group_id == student_group.pk
    student_group = StudentGroupService.resolve(course, student_profile=student_profile2)
    enrollment = EnrollmentService.enroll(student_profile2, course,
                                          reason_entry='test enrollment',
                                          student_group=student_group)
    assert enrollment.student_group == student_group


@pytest.mark.django_db
def test_enrollment_capacity(settings, program_cub001, program_run_cub):
    student_profile = StudentProfileFactory(academic_program_enrollment=program_run_cub)
    current_semester = SemesterFactory.create_current()
    course = CourseFactory.create(semester=current_semester,
                                  capacity=1)
    CourseProgramBindingFactory(course=course, program=program_cub001)
    student_group = course.student_groups.first()
    student_profile_2 = StudentProfileFactory(academic_program_enrollment=program_run_cub)
    EnrollmentService.enroll(student_profile_2, course, student_group=student_group)
    course.refresh_from_db()
    assert course.places_left == 0
    assert Enrollment.active.count() == 1
    with pytest.raises(CourseCapacityFull):
        EnrollmentService.enroll(student_profile, course, student_group=student_group)
    # Make sure enrollment record created by enrollment service
    # was rollbacked by transaction context manager
    assert Enrollment.objects.count() == 1


@pytest.mark.django_db
def test_enrollment_capacity_view(client, program_cub001, program_run_cub):
    student_profile = StudentProfileFactory(academic_program_enrollment=program_run_cub)
    student = student_profile.user
    client.login(student)
    course = CourseFactory()
    CourseProgramBindingFactory(course=course, program=program_cub001)
    response = client.get(course.get_absolute_url())
    assert smart_bytes(_("Places available")) not in response.content
    course.capacity = 1
    course.save()
    response = client.get(course.get_absolute_url())
    assert smart_bytes(_("Places available")) in response.content
    form = {'course_pk': course.pk}
    client.post(course.get_enroll_url(), form)
    assert 1 == Enrollment.active.filter(student=student, course=course).count()
    # Capacity is reached
    course.refresh_from_db()
    assert course.learners_count == 1
    assert course.places_left == 0
    s2 = StudentFactory(student_profile__academic_program_enrollment=program_run_cub)
    client.login(s2)
    response = client.get(course.get_absolute_url())
    assert smart_bytes(_("Enroll in")) not in response.content
    # POST request should be rejected
    response = client.post(course.get_enroll_url(), form)
    assert response.status_code == 302
    # Increase capacity
    course.capacity += 1
    course.save()
    assert course.places_left == 1
    response = client.get(course.get_absolute_url())
    assert (smart_bytes(_("Places available")) + b": 1") in response.content
    # Unenroll first student, capacity should increase
    client.login(student)
    response = client.post(course.get_unenroll_url(), form)
    assert Enrollment.active.filter(course=course).count() == 0
    course.refresh_from_db()
    assert course.learners_count == 0
    response = client.get(course.get_absolute_url())
    assert (smart_bytes(_("Places available")) + b": 2") in response.content


@pytest.mark.django_db
@pytest.mark.parametrize("inactive_status", StudentStatuses.inactive_statuses)
def test_enrollment_inactive_student(inactive_status, client, settings, program_cub001, program_run_cub):
    student = StudentFactory(
        student_profile__academic_program_enrollment=program_run_cub
    )
    client.login(student)
    course = CourseFactory()
    CourseProgramBindingFactory(course=course, program=program_cub001)
    response = client.get(course.get_absolute_url())
    assert response.status_code == 200
    assert smart_bytes(_("Enroll in")) in response.content
    student_profile = get_student_profile(student)
    student_profile.status = inactive_status
    student_profile.save()
    response = client.get(course.get_absolute_url())
    assert smart_bytes(_("Enroll in")) not in response.content


@pytest.mark.django_db
@pytest.mark.parametrize('group_mode', [
    CourseGroupModes.MANUAL,
    CourseGroupModes.PROGRAM,
    CourseGroupModes.PROGRAM_RUN,
])
def test_enrollment(client, program_cub001, program_run_cub, group_mode):
    student1, student2 = StudentFactory.create_batch(
        2, student_profile__academic_program_enrollment=program_run_cub
    )
    client.login(student1)
    today = now_local(student1.time_zone)
    current_semester = SemesterFactory.create_current()
    course = CourseFactory(semester=current_semester, group_mode=group_mode)
    CourseProgramBindingFactory(course=course, program=program_cub001)
    url = course.get_enroll_url()
    form = {'course_pk': course.pk}
    response = client.post(url, form)
    assert response.status_code == 302
    assert course.enrollment_set.count() == 1
    as_ = AssignmentFactory.create_batch(3, course=course)
    assert set((student1.pk, a.pk) for a in as_) == set(StudentAssignment.objects
                                                        .filter(student=student1)
                                                        .values_list('student', 'assignment'))
    co_other = CourseFactory(semester=current_semester)
    CourseProgramBindingFactory(course=co_other, program=program_cub001)
    form.update({'back': 'study:course_list'})
    url = co_other.get_enroll_url()
    response = client.post(url, form)
    assert response.status_code == 302
    assert co_other.enrollment_set.count() == 1
    assert course.enrollment_set.count() == 1
    # Try to enroll to old CO
    old_semester = SemesterFactory.create(year=2010)
    old_co = CourseFactory.create(semester=old_semester)
    form = {'course_pk': old_co.pk}
    url = old_co.get_enroll_url()
    assert client.post(url, form).status_code == 403


@pytest.mark.django_db
def test_enrollment_reason_entry(client, program_cub001, program_run_cub):
    student_profile = StudentProfileFactory(academic_program_enrollment=program_run_cub)
    client.login(student_profile.user)
    today = now_local(student_profile.user.time_zone)
    course = CourseFactory()
    CourseProgramBindingFactory(course=course, program=program_cub001)
    form = {'course_pk': course.pk, 'reason': 'foo'}
    client.post(course.get_enroll_url(), form)
    assert Enrollment.active.count() == 1
    date = today.strftime(DATE_FORMAT_RU)
    assert Enrollment.objects.first().reason_entry == f'{date}\nfoo\n\n'
    client.post(course.get_unenroll_url(), form)
    assert Enrollment.active.count() == 0
    assert Enrollment.objects.first().reason_entry == f'{date}\nfoo\n\n'
    # Enroll for the second time, first entry reason should be saved
    form['reason'] = 'bar'
    client.post(course.get_enroll_url(), form)
    assert Enrollment.active.count() == 1
    assert Enrollment.objects.first().reason_entry == f'{date}\nbar\n\n{date}\nfoo\n\n'


@pytest.mark.django_db
def test_enrollment_leave_reason(client, program_cub001, program_run_cub):
    student_profile = StudentProfileFactory(academic_program_enrollment=program_run_cub)
    client.login(student_profile.user)
    today = now_local(student_profile.user.time_zone)
    current_semester = SemesterFactory.create_current()
    co = CourseFactory(semester=current_semester)
    CourseProgramBindingFactory(course=co, program=program_cub001)
    form = {'course_pk': co.pk}
    client.post(co.get_enroll_url(), form)
    assert Enrollment.active.count() == 1
    assert Enrollment.objects.first().reason_entry == ''
    form['reason'] = 'foo'
    client.post(co.get_unenroll_url(), form)
    assert Enrollment.active.count() == 0
    e = Enrollment.objects.first()
    assert today.strftime(DATE_FORMAT_RU) in e.reason_leave
    assert 'foo' in e.reason_leave
    # Enroll for the second time and leave with another reason
    client.post(co.get_enroll_url(), form)
    assert Enrollment.active.count() == 1
    form['reason'] = 'bar'
    client.post(co.get_unenroll_url(), form)
    assert Enrollment.active.count() == 0
    e = Enrollment.objects.first()
    assert 'foo' in e.reason_leave
    assert 'bar' in e.reason_leave
    co_other = CourseFactory.create(semester=current_semester)
    CourseProgramBindingFactory(course=co_other, program=program_cub001)
    client.post(co_other.get_enroll_url(), {})
    e_other = Enrollment.active.filter(course=co_other).first()
    assert not e_other.reason_entry
    assert not e_other.reason_leave


@pytest.mark.django_db
def test_unenrollment(client, settings, assert_redirect, program_cub001, program_run_cub):
    student = StudentFactory(student_profile__academic_program_enrollment=program_run_cub)
    client.login(student)
    current_semester = SemesterFactory.create_current()
    course = CourseFactory(semester=current_semester)
    binding = CourseProgramBindingFactory(course=course, program=program_cub001)
    as_ = AssignmentFactory.create_batch(3, course=course)
    form = {'course_pk': course.pk}
    # Enrollment already closed
    binding.enrollment_end_date = timezone.now() - datetime.timedelta(days=1)
    binding.save()
    response = client.post(course.get_enroll_url(), form)
    assert response.status_code == 403
    binding.enrollment_end_date = timezone.now() + datetime.timedelta(days=1)
    binding.save()
    response = client.post(course.get_enroll_url(), form, follow=True)
    assert response.status_code == 200
    assert Enrollment.objects.count() == 1
    response = client.get(course.get_absolute_url())
    assert smart_bytes("Unenroll") in response.content
    assert smart_bytes(course) in response.content
    assert Enrollment.objects.count() == 1
    enrollment = Enrollment.objects.first()
    assert not enrollment.is_deleted
    client.post(course.get_unenroll_url(), form)
    assert Enrollment.active.filter(student=student, course=course).count() == 0
    assert Enrollment.objects.count() == 1
    enrollment = Enrollment.objects.first()
    enrollment_id = enrollment.pk
    assert enrollment.is_deleted
    # Make sure student progress won't been deleted
    a_ss = (StudentAssignment.objects.filter(student=student,
                                             assignment__course=course))
    assert len(a_ss) == 3
    # On re-enroll use old record
    client.post(course.get_enroll_url(), form)
    assert Enrollment.objects.count() == 1
    enrollment = Enrollment.objects.first()
    assert enrollment.pk == enrollment_id
    assert not enrollment.is_deleted
    # Check ongoing courses on student courses page are not empty
    response = client.get(reverse("study:course_list"))
    assert len(response.context_data['ongoing_rest']) == 0
    assert len(response.context_data['ongoing_enrolled']) == 1
    assert len(response.context_data['archive']) == 0
    # Check `back` url on unenroll action
    url = course.get_unenroll_url() + "?back=study:course_list"
    assert_redirect(client.post(url, form),
                    reverse('study:course_list'))
    assert set(a_ss) == set(StudentAssignment.objects
                            .filter(student=student,
                                    assignment__course=course))
    # Check courses on student courses page are empty
    response = client.get(reverse("study:course_list"))
    assert len(response.context_data['ongoing_rest']) == 1
    assert len(response.context_data['ongoing_enrolled']) == 0
    assert len(response.context_data['archive']) == 0


@pytest.mark.django_db
def test_reenrollment(client, program_cub001, program_run_cub):
    """Create assignments for student if they left the course and come back"""
    student = StudentFactory(
        student_profile__academic_program_enrollment=program_run_cub
    )
    course = CourseFactory(group_mode=CourseGroupModes.PROGRAM)
    binding_cub = CourseProgramBindingFactory(course=course, program=program_cub001)
    binding_other = CourseProgramBindingFactory(course=course)
    program_other = binding_other.program
    assignment = AssignmentFactory(course=course)
    e = EnrollmentFactory(student=student, course=course)
    assert not e.is_deleted
    assert StudentAssignment.objects.filter(student_id=student.pk).count() == 1
    # Deactivate student enrollment
    e.is_deleted = True
    e.save()
    assert Enrollment.active.count() == 0
    assignment2 = AssignmentFactory(course=course)
    sg = StudentGroup.objects.get(course=course, program=program_other)
    # This assignment is restricted for student's group
    assignment3 = AssignmentFactory(course=course, restricted_to=[sg])
    assert StudentAssignment.objects.filter(student_id=student.pk).count() == 1
    client.login(student)
    form = {'course_pk': course.pk}
    response = client.post(course.get_enroll_url(), form, follow=True)
    assert response.status_code == 200
    e.refresh_from_db()
    assert StudentAssignment.objects.filter(student_id=student.pk).count() == 2


@pytest.mark.django_db
def test_enrollment_in_other_university(client, program_cub001, program_run_cub, program_run_nup):
    semester = SemesterFactory.create_current()
    course_cub = CourseFactory(semester=semester)
    CourseProgramBindingFactory(course=course_cub, program=program_cub001)
    student_profile_cub = StudentProfileFactory(academic_program_enrollment=program_run_cub)
    assert student_profile_cub.user.has_perm(
        EnrollInCourse.name,
        EnrollOrLeavePermissionObject(course_cub, student_profile_cub)
    )
    student_profile_nup = StudentProfileFactory(academic_program_enrollment=program_run_nup)
    client.login(student_profile_cub.user)
    form = {'course_pk': course_cub.pk}
    response = client.post(course_cub.get_enroll_url(), form)
    assert response.status_code == 302
    assert Enrollment.objects.count() == 1
    client.login(student_profile_nup.user)
    response = client.post(course_cub.get_enroll_url(), form)
    assert response.status_code == 403
    assert Enrollment.objects.count() == 1
    student_profile = StudentProfileFactory(
        academic_program_enrollment=AcademicProgramRunFactory()
    )
    # Check button visibility
    Enrollment.objects.all().delete()
    client.login(student_profile_cub.user)
    response = client.get(course_cub.get_absolute_url())
    html = BeautifulSoup(response.content, "html.parser")
    buttons = (html.find("div", {"class": "o-buttons-vertical"})
               .find_all(attrs={'class': 'btn'}))
    assert any("Enroll in" in s.text for s in buttons)
    for user in [student_profile_nup.user, student_profile.user]:
        client.login(user)
        response = client.get(course_cub.get_absolute_url())
        assert smart_bytes("Enroll in") not in response.content


@pytest.mark.django_db
def test_view_course_multiple_programs(client, program_cub001, program_run_cub, program_nup001, program_run_nup):
    """
    Student can enroll in the course if it is available to the student program
    """
    semester = SemesterFactory.create_current()
    course = CourseFactory(semester=semester)
    CourseProgramBindingFactory(course=course, program=program_cub001)
    student_cub = StudentFactory(
        student_profile__academic_program_enrollment=program_run_cub
    )
    student_profile = student_cub.get_student_profile()
    assert student_cub.has_perm(
        EnrollInCourse.name,
        EnrollOrLeavePermissionObject(course, student_profile)
    )
    student_nup = StudentFactory(
        student_profile__academic_program_enrollment=program_run_nup
    )
    form = {'course_pk': course.pk}
    client.login(student_cub)
    response = client.post(course.get_enroll_url(), form)
    assert response.status_code == 302
    assert Enrollment.objects.count() == 1
    client.login(student_nup)
    response = client.post(course.get_enroll_url(), form)
    assert response.status_code == 403
    CourseProgramBindingFactory(course=course, program=program_nup001)
    response = client.post(course.get_enroll_url(), form)
    assert response.status_code == 302
    assert Enrollment.objects.count() == 2


@pytest.mark.django_db
def test_course_enrollment_is_open(client, settings, program_cub001, program_run_cub):
    now = timezone.now()
    yesterday = now - datetime.timedelta(days=1)
    tomorrow = now + datetime.timedelta(days=1)
    term = SemesterFactory.create_current()
    course = CourseFactory(semester=term, completed_at=tomorrow.date())
    binding = CourseProgramBindingFactory(course=course, program=program_cub001)
    student_profile = StudentProfileFactory(academic_program_enrollment=program_run_cub)
    student = student_profile.user
    perm_obj = EnrollOrLeavePermissionObject(course, student_profile)
    assert student.has_perm(EnrollInCourse.name, perm_obj)
    client.login(student)
    response = client.get(course.get_absolute_url())
    html = BeautifulSoup(response.content, "html.parser")
    buttons = (html.find("div", {"class": "o-buttons-vertical"})
               .find_all(attrs={'class': 'btn'}))
    assert any("Enroll in" in s.text for s in buttons)
    default_completed_at = course.completed_at
    course.completed_at = now.date()
    course.save()
    response = client.get(course.get_absolute_url())
    assert smart_bytes("Enroll in") not in response.content
    course.completed_at = default_completed_at
    course.save()
    assert student.has_perm(EnrollInCourse.name, perm_obj)
    response = client.get(course.get_absolute_url())
    assert smart_bytes("Enroll in") in response.content
    binding.enrollment_end_date = yesterday
    binding.save()
    response = client.get(course.get_absolute_url())
    assert smart_bytes("Enroll in") not in response.content


@pytest.mark.django_db
def test_enrollment_by_invitation(settings, client, program_cub001):
    semester = SemesterFactory.create_current()
    course_invitation = CourseInvitationBindingFactory(course__semester=semester)
    course = course_invitation.course
    CourseProgramBindingFactory(course=course, program=program_cub001)
    enroll_url = course.get_enroll_url()
    invited = InvitedStudentFactory()
    client.login(invited)

    response = client.post(enroll_url, {})
    assert response.status_code == 403

    response = client.post(course_invitation.invitation.get_absolute_url())
    assert response.status_code == 302

    response = client.post(enroll_url, {})
    assert response.status_code == 302

    enrollments = Enrollment.active.filter(student=invited, course=course).all()
    assert len(enrollments) == 1
    assert enrollments[0].course_program_binding == course_invitation


@pytest.mark.django_db
def test_enrollment_populate_assignments(client, program_cub001, program_run_cub, program_nup001):
    student_profile = StudentProfileFactory(
        academic_program_enrollment=program_run_cub
    )
    student = student_profile.user
    course = CourseFactory(group_mode=CourseGroupModes.PROGRAM)
    CourseProgramBindingFactory(course=course, program=program_cub001)
    CourseProgramBindingFactory(course=course, program=program_nup001)
    assert StudentGroup.objects.filter(course=course).count() == 2
    student_group_cub = StudentGroup.objects.get(program=program_cub001)
    student_group_nup = StudentGroup.objects.get(program=program_nup001)
    assignment_all = AssignmentFactory(course=course)
    assignment_spb = AssignmentFactory(course=course, restricted_to=[student_group_cub])
    assignment_nsk = AssignmentFactory(course=course, restricted_to=[student_group_nup])
    assert StudentAssignment.objects.count() == 0
    form = {'course_pk': course.pk}
    client.login(student)
    enroll_url = course.get_enroll_url()
    response = client.post(enroll_url, form)
    assert response.status_code == 302
    assert course.enrollment_set.count() == 1
    student_assignments = StudentAssignment.objects.filter(student=student)
    assert student_assignments.count() == 2
    assignments = [sa.assignment for sa in student_assignments]
    assert assignment_all in assignments
    assert assignment_spb in assignments


@pytest.mark.django_db
def test_enrollment_by_invitation_normal_student_newer_program_run(client, program_cub001):
    meta_course = MetaCourseFactory()
    course_2024 = CourseFactory(meta_course=meta_course)
    CourseProgramBindingFactory(course=course_2024, program=program_cub001, start_year_filter=[2024])
    course_2025 = CourseFactory(meta_course=meta_course)
    binding_2025 = CourseProgramBindingFactory(course=course_2025, program=program_cub001, start_year_filter=[2025])

    program_run_2024 = AcademicProgramRunFactory(program=program_cub001, start_year=2024)
    program_run_2025 = AcademicProgramRunFactory(program=program_cub001, start_year=2025)
    student_profile = StudentProfileFactory(academic_program_enrollment=program_run_2024)
    student = student_profile.user
    client.login(student)

    response = client.get(course_2024.get_absolute_url())
    assert smart_bytes("Enroll in") in response.content
    response = client.get(course_2025.get_absolute_url())
    assert smart_bytes("Enroll in") not in response.content

    course_invitation = CourseInvitationBindingFactory(course=course_2025)
    invitation = course_invitation.invitation
    use_invitation_url = invitation.get_absolute_url()
    response = client.post(use_invitation_url)
    assert response.status_code == 302

    response = client.get(course_2025.get_absolute_url())
    assert smart_bytes("Enroll in") in response.content
    client.post(course_2025.get_enroll_url())
    enrollments = Enrollment.active.filter(student=student, course=course_2025).all()
    assert len(enrollments) == 1
    assert enrollments[0].course_program_binding == course_invitation


@pytest.mark.django_db
def test_enrollment_by_invitation_normal_student_other_program(
    client, program_cub001, program_nup001, program_run_cub, program_run_nup,
):
    meta_course = MetaCourseFactory()
    course_cub = CourseFactory(meta_course=meta_course)
    CourseProgramBindingFactory(course=course_cub, program=program_cub001)
    course_nup = CourseFactory(meta_course=meta_course)
    binding_nup = CourseProgramBindingFactory(course=course_nup, program=program_nup001)

    student_profile = StudentProfileFactory(academic_program_enrollment=program_run_cub)
    student = student_profile.user
    client.login(student)

    response = client.get(course_cub.get_absolute_url())
    assert smart_bytes("Enroll in") in response.content
    response = client.get(course_nup.get_absolute_url())
    assert smart_bytes("Enroll in") not in response.content

    course_invitation = CourseInvitationBindingFactory(course=course_nup)
    invitation = course_invitation.invitation
    use_invitation_url = invitation.get_absolute_url()
    response = client.post(use_invitation_url)
    assert response.status_code == 302

    response = client.get(course_nup.get_absolute_url())
    assert smart_bytes("Enroll in") in response.content
    client.post(course_nup.get_enroll_url())
    enrollments = Enrollment.active.filter(student=student, course=course_nup).all()
    assert len(enrollments) == 1
    assert enrollments[0].course_program_binding == course_invitation


@pytest.mark.django_db
def test_enrollment_available_in_program_and_invitation(client, program_cub001, program_run_cub):
    student_profile = StudentProfileFactory(academic_program_enrollment=program_run_cub)
    user = student_profile.user

    course = CourseFactory()
    course_program = CourseProgramBindingFactory(course=course, program=program_cub001)
    course_invitation = CourseInvitationBindingFactory(course=course)

    client.login(user)
    response = client.get(course.get_absolute_url())
    assert response.status_code == 200
    assert b'Enroll in' in response.content

    response = client.post(course.get_enroll_url())
    assert response.status_code == 302

    enrollments = Enrollment.active.filter(student=user, course=course).all()
    assert len(enrollments) == 1
    assert enrollments[0].course_program_binding == course_program
