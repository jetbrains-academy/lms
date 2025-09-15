import pytest

from core.urls import reverse
from courses.tests.factories import CourseProgramBindingFactory
from learning.tests.factories import EnrollmentFactory
from users.models import StudentTypes
from users.tests.factories import StudentFactory


@pytest.mark.django_db
def test_alumni_enrollment(client):
    # Create some regular students and courses
    EnrollmentFactory.create_batch(3)
    # Create alumni student and test it
    student = StudentFactory(student_profile__type=StudentTypes.ALUMNI)
    client.login(student)
    binding = CourseProgramBindingFactory(
        program=None,
        is_alumni=True,
    )
    course = binding.course
    list_url = reverse('study:course_list')
    response = client.get(list_url)
    assert response.status_code == 200
    assert response.context_data['ongoing_enrolled'] == []
    assert response.context_data['ongoing_rest'] == [course]
    assert response.context_data['archive'] == []

    response = client.post(
        course.get_enroll_url(),
        {'course_pk': course.pk},
    )
    assert response.status_code == 302
    response = client.get(list_url)
    assert response.status_code == 200
    assert response.context_data['ongoing_enrolled'] == [course]
    assert response.context_data['ongoing_rest'] == []
    assert response.context_data['archive'] == []
