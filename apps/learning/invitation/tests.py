import factory
import pytest

from core.urls import reverse
from courses.tests.factories import (
    CourseProgramBindingFactory,
    AssignmentFactory,
    SemesterFactory,
)
from learning.invitation.views import create_invited_profile
from learning.models import StudentAssignment
from learning.tests.factories import (
    CourseInvitationBindingFactory,
    InvitationFactory,
    EnrollmentFactory,
)
from users.forms import StudentCreationForm
from users.models import StudentProfile, User, StudentTypes
from users.tests.factories import (
    UserFactory,
    StudentProfileFactory,
)


def create_student_profile_with_courses(
    student_type: StudentTypes, *, n_courses: int
) -> StudentProfile:
    student_profile: StudentProfile = StudentProfileFactory(type=student_type)
    match student_type:
        case StudentTypes.REGULAR:
            binding_args = {'program': student_profile.academic_program_enrollment.program}
        case StudentTypes.INVITED:
            binding_args = {'invitation': student_profile.invitation, 'program': None}
        case StudentTypes.ALUMNI:
            binding_args = {'is_alumni': True, 'program': None}
        case _:
            raise ValueError(f'Unknown student type {student_type}')

    semester = SemesterFactory.create_current()
    for _ in range(n_courses):
        CourseProgramBindingFactory(course__semester=semester, **binding_args)

    return student_profile


@pytest.mark.django_db
def test_view_invitation_create_user(client):
    invitation = InvitationFactory()
    url = invitation.get_absolute_url()
    response = client.get(url)
    assert response.status_code == 200
    assert isinstance(response.context['form'], StudentCreationForm)
    form_data = factory.build(dict, FACTORY_CLASS=UserFactory)
    form_data['terms_accepted'] = True
    form_data['password1'] = form_data['password2'] = form_data['password']
    response = client.post(url, form_data)
    assert response.status_code == 302

    user = User.objects.get(username=form_data['username'])
    assert user
    user.raw_password = form_data['password']

    profiles = StudentProfile.objects.filter(user=user).all()
    assert len(profiles) == 1
    assert profiles[0].invitation == invitation
    assert invitation in profiles[0].invitations.all()

    client.login(user)

    # Duplicate profiles should not be created
    response = client.get(url)
    assert response.status_code == 302
    response = client.post(url, form_data)
    assert response.status_code == 302
    assert StudentProfile.objects.filter(user=user).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize('student_type', StudentTypes.values)
def test_view_invitation_add_invitation_to_existing_profile(
    client, student_type: StudentTypes,
):
    student_profile = create_student_profile_with_courses(student_type, n_courses=3)
    user = student_profile.user
    client.login(user)

    invitation = InvitationFactory()
    CourseInvitationBindingFactory(invitation=invitation)
    url = invitation.get_absolute_url()
    response = client.get(url)
    assert response.status_code == 200
    response = client.post(url)
    assert response.status_code == 302

    profiles = StudentProfile.objects.filter(user=user).all()
    assert len(profiles) == 1
    # Should be the original invitation in case of invited student
    # or None in case of regular student
    assert profiles[0].invitation != invitation
    assert invitation in profiles[0].invitations.all()

    # Duplicate invitations should not be added
    response = client.get(url)
    assert response.status_code == 302
    response = client.post(url)
    assert response.status_code == 302
    assert StudentProfile.objects.filter(user=user).count() == 1

    response = client.get(reverse('study:course_list'))
    assert response.status_code == 200
    assert len(response.context_data['ongoing_rest']) == 4


@pytest.mark.django_db
def test_invitation_view_enrolled_students_log(
    client, lms_resolver, assert_redirect, settings
):
    course_invitation = CourseInvitationBindingFactory()
    invitation = course_invitation.invitation
    url = invitation.get_absolute_url()
    client.post(url)
    # Anonymous user working
    assert not invitation.enrolled_students.count()

    user = UserFactory()
    client.login(user)

    create_invited_profile(user, invitation)
    response = client.post(url)
    assert response.status_code == 302
    # User with completed profile should be added to enrolled_students set
    assert invitation.enrolled_students.count() == 1

    response = client.post(url)
    assert response.status_code == 302
    # There should be no double entry
    assert invitation.enrolled_students.count() == 1

    user_two = UserFactory()
    create_invited_profile(user_two, invitation)
    client.login(user_two)
    response = client.post(url)
    assert response.status_code == 302
    profile_one = user.get_student_profile()
    profile_two = user_two.get_student_profile()
    assert set(invitation.enrolled_students.all()) == {profile_one, profile_two}


@pytest.mark.django_db
def test_view_assignments_as_invited(client):
    student_profile = create_student_profile_with_courses(StudentTypes.INVITED, n_courses=1)
    course_binding = student_profile.invitation.bindings.first()
    course = course_binding.course
    client.login(student_profile.user)

    EnrollmentFactory(
        student_profile=student_profile,
        student=student_profile.user,
        course=course,
        course_program_binding=course_binding,
    )
    assignment = AssignmentFactory(course=course)
    personal_assignment = StudentAssignment.objects.filter(
        assignment=assignment, student=student_profile.user
    ).get()

    assignments_list_url = reverse('study:assignment_list')
    response = client.get(assignments_list_url)
    assert response.status_code == 200
    assert len(response.context_data['assignment_list_open']) == 1

    detail_url = personal_assignment.get_student_url()
    create_solution_url = reverse(
        'study:assignment_solution_create', kwargs={"pk": personal_assignment.pk}
    )
    form_data = {'solution-text': 'Test solution'}
    response = client.post(create_solution_url, form_data)
    assert response.status_code == 302
    assert response.url == detail_url
