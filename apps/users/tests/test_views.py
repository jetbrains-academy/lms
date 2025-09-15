import copy

import factory
import pytest
import pytz
from bs4 import BeautifulSoup
from django.conf import settings
from django.forms.models import model_to_dict
from django.utils.encoding import smart_bytes, smart_str
from django_recaptcha.client import RecaptchaResponse

from auth.mixins import RolePermissionRequiredMixin
from core.admin import get_admin_url
from core.urls import reverse
from courses.tests.factories import CourseFactory
from learning.tests.factories import EnrollmentFactory
from users.constants import GenderTypes, Roles
from users.forms import UserCreationForm, StudentCreationForm, StudentEnrollmentForm
from users.models import User, UserGroup, StudentProfile
from users.permissions import ViewAccountConnectedServiceProvider
from users.tests.factories import (
    CuratorFactory, StudentFactory,
    StudentProfileFactory, UserFactory, add_user_groups, SubmissionFormFactory, TeacherFactory
)


@pytest.mark.django_db
def test_abbreviated_name(client):
    user = User(first_name=u"Анна", last_name=u"Иванова")
    assert user.get_abbreviated_name() == "А. Иванова"


@pytest.mark.django_db
def test_short_name(client):
    user = User(first_name="Анна", last_name="Иванова")
    assert user.get_short_name() == "Анна Иванова"


@pytest.mark.django_db
def test_to_string(client):
    user = User(first_name=u"Анна", last_name=u"Иванова")
    assert smart_str(user) == user.get_full_name(True)


@pytest.mark.django_db
def test_login_page(client):
    response = client.get(reverse('auth:login'))
    soup = BeautifulSoup(response.content, "html.parser")
    maybe_form = soup.find_all("form")
    assert len(maybe_form) == 1
    form = maybe_form[0]
    assert len(form.select('input[name="username"]')) == 1
    assert len(form.select('input[name="password"]')) == 1
    assert len(form.select('input[type="submit"]')) == 1


@pytest.mark.django_db
def test_login_works(client, mocker):
    mocked_submit = mocker.patch('django_recaptcha.fields.client.submit')
    mocked_submit.return_value = RecaptchaResponse(is_valid=True)
    good_user_attrs = factory.build(dict, FACTORY_CLASS=UserFactory)
    good_user = UserFactory(**good_user_attrs)
    add_user_groups(good_user, [Roles.STUDENT])
    assert '_auth_user_id' not in client.session
    good_user_attrs['g-recaptcha-response'] = 'definitely not a valid response'
    bad_user = copy.copy(good_user_attrs)
    bad_user['password'] = "BAD"
    response = client.post(reverse('auth:login'), bad_user)
    assert '_auth_user_id' not in client.session
    assert response.status_code == 200
    assert len(response.context['form'].errors) > 0
    response = client.post(reverse('auth:login'), good_user_attrs)
    assert response.status_code == 302
    # students redirected to /learning/assignments/
    assert response.url == '/learning/assignments/'
    assert '_auth_user_id' in client.session


@pytest.mark.django_db
def test_logout_works(client):
    user = UserFactory()
    client.login(user)
    assert '_auth_user_id' in client.session
    response = client.get(reverse('auth:logout'))
    assert response.status_code == 302
    assert response.url == settings.LOGOUT_REDIRECT_URL
    assert '_auth_user_id' not in client.session


@pytest.mark.django_db
def test_logout_redirect_works(client):
    user = UserFactory()
    client.login(user)
    response = client.get(reverse('auth:logout'),
                          {'next': "/abc"})
    assert response.status_code == 302
    assert response.url == "/abc"


@pytest.mark.django_db
def test_short_bio(client):
    """
    `get_short_bio` split bio on the first paragraph
    """
    user = UserFactory()
    user.bio = "Some small text"
    assert user.get_short_bio() == "Some small text"
    user.bio = """Some large text.

    It has several paragraphs, by the way."""
    assert user.get_short_bio() == "Some large text."


@pytest.mark.django_db
def test_duplicate_check(client):
    """
    It should be impossible to create users with equal names
    """
    user = UserFactory()
    form_data = {'username': user.username,
                 'email': user.email,
                 'gender': GenderTypes.MALE,
                 'time_zone': pytz.utc,
                 'password1': "test123foobar@!",
                 'password2': "test123foobar@!"}
    form = UserCreationForm(data=form_data)
    assert not form.is_valid()
    new_user = UserFactory.build()
    form_data.update({
        'username': new_user.username,
        'email': new_user.email
    })
    form = UserCreationForm(data=form_data)
    assert form.is_valid()


@pytest.mark.django_db
def test_student_cannot_view_other_student_profiles(client):
    student1 = StudentFactory()
    student2 = StudentFactory()
    client.login(student1)
    student2_profile = student2.get_absolute_url()
    response = client.get(student2_profile)
    assert response.status_code == 403


@pytest.mark.django_db
def test_profile_detail_personal_data(client):
    """
    Personal data, such as email, attended courses and student profiles
    should only be visible to the students themselves and curators
    """
    student_mail = "student@student.mail"
    student = StudentFactory(email=student_mail)
    client.login(student)
    url = student.get_absolute_url()

    course_name = 'test_course'
    course = CourseFactory(meta_course__name=course_name)
    EnrollmentFactory(student=student, course=course)

    response = client.get(url)
    assert response.status_code == 200
    assert smart_bytes(student_mail) in response.content
    assert smart_bytes(course_name) in response.content
    assert response.context_data['profile_user'] == student
    assert response.context_data['can_edit_profile']
    assert 'student_profiles' in response.context_data

    curator = CuratorFactory()
    client.login(curator)
    response = client.get(url)
    assert response.status_code == 200
    assert smart_bytes(student_mail) in response.content
    assert smart_bytes(course_name) in response.content
    assert response.context_data['profile_user'] == student
    assert response.context_data['can_edit_profile']
    assert 'student_profiles' in response.context_data

    teacher = TeacherFactory()
    course.teachers.add(teacher)
    client.login(teacher)
    response = client.get(url)
    assert response.status_code == 200
    assert smart_bytes(student_mail) in response.content
    assert smart_bytes(course_name) not in response.content
    assert response.context_data['profile_user'] == student
    assert not response.context_data['can_edit_profile']
    assert 'student_profiles' not in response.context_data


@pytest.mark.django_db
def test_view_user_can_update_profile(client, assert_redirect):
    test_note = "The best user in the world"
    user = StudentFactory()
    client.login(user)
    response = client.get(user.get_absolute_url())
    assert response.status_code == 200
    assert response.context_data['profile_user'] == user
    assert response.context_data['can_edit_profile']
    assert smart_bytes(user.get_update_profile_url()) in response.content
    response = client.get(user.get_update_profile_url())
    assert b'bio' in response.content
    form_data = {
        'time_zone': user.time_zone,
        'bio': test_note
    }
    response = client.post(user.get_update_profile_url(), form_data)
    assert_redirect(response, user.get_absolute_url())
    response = client.get(user.get_absolute_url())
    assert smart_bytes(test_note) in response.content


@pytest.mark.django_db
def test_view_user_cannot_change_jba(client, assert_redirect):
    email1 = 'test1@example.com'
    email2 = 'test2@example.com'
    user = StudentFactory()
    client.login(user)
    form_data = {
        'time_zone': user.time_zone,
        'jetbrains_account': email1,
    }
    resp = client.post(user.get_update_profile_url(), form_data)
    assert_redirect(resp, user.get_absolute_url())
    user.refresh_from_db()
    assert user.jetbrains_account == email1

    resp = client.get(user.get_update_profile_url())
    jba_field = resp.context_data['form'].fields['jetbrains_account']
    assert jba_field.disabled
    assert jba_field.help_text == 'To change this field, please contact your curator'

    form_data = {
        'time_zone': user.time_zone,
        'jetbrains_account': email2,
    }
    resp = client.post(user.get_update_profile_url(), form_data)
    assert_redirect(resp, user.get_absolute_url())
    user.refresh_from_db()
    assert user.jetbrains_account == email1

    # Test that user can't reset jetbrains_account
    form_data = {
        'time_zone': user.time_zone,
        'jetbrains_account': '',
    }
    resp = client.post(user.get_update_profile_url(), form_data)
    assert_redirect(resp, user.get_absolute_url())
    user.refresh_from_db()
    assert user.jetbrains_account == email1

    # Test that if reset manually, the field can be changed again
    user.jetbrains_account = ''
    user.save()
    form_data = {
        'time_zone': user.time_zone,
        'jetbrains_account': email2,
    }
    resp = client.post(user.get_update_profile_url(), form_data)
    assert_redirect(resp, user.get_absolute_url())
    user.refresh_from_db()
    assert user.jetbrains_account == email2


@pytest.mark.django_db
def test_student_should_have_profile(client):
    client.login(CuratorFactory())
    user = UserFactory(photo='/a/b/c')
    assert user.groups.count() == 0
    form_data = {k: v for k, v in model_to_dict(user).items() if v is not None}
    del form_data['photo']
    form_data.update({
        # Django wants all inline formsets
        'groups-TOTAL_FORMS': '1',
        'groups-INITIAL_FORMS': '0',
        'groups-MAX_NUM_FORMS': '',
        'groups-0-user': user.pk,
        'groups-0-role': Roles.STUDENT,
        'groups-0-site': settings.SITE_ID,
    })
    admin_url = get_admin_url(user)
    response = client.post(admin_url, form_data)
    assert response.status_code == 200

    def get_user_group_formset(response):
        form = None
        for inline_formset_obj in response.context['inline_admin_formsets']:
            if issubclass(inline_formset_obj.formset.model, UserGroup):
                form = inline_formset_obj.formset
        assert form, "Inline form for UserGroup is missing"
        return form

    user_group_form = get_user_group_formset(response)
    assert not user_group_form.is_valid()
    StudentProfileFactory(user=user)
    UserGroup.objects.filter(user=user).delete()
    response = client.post(admin_url, form_data)
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.groups.count() == 1


@pytest.mark.django_db
def test_view_user_detail_connected_providers(client, settings):
    if not settings.IS_SOCIAL_ACCOUNTS_ENABLED:
        pytest.skip()
    user1, user2 = UserFactory.create_batch(2)
    client.login(user1)
    response = client.get(user1.get_absolute_url())
    assert response.status_code == 200
    assert 'available_providers' in response.context_data
    assert isinstance(response.context_data['available_providers'], list)
    client.login(user2)
    response = client.get(user1.get_absolute_url())
    assert response.status_code == 200
    assert response.context_data['available_providers'] is False
    client.login(CuratorFactory())
    response = client.get(user1.get_absolute_url())
    assert response.status_code == 200
    assert isinstance(response.context_data['available_providers'], list)


@pytest.mark.django_db
def test_view_connected_auth_services_smoke(client, settings, lms_resolver):
    if not settings.IS_SOCIAL_ACCOUNTS_ENABLED:
        pytest.skip()
    user1, user2 = UserFactory.create_batch(2)
    url = reverse('api:connected_accounts', subdomain=settings.LMS_SUBDOMAIN, kwargs={
        'user': user1.pk
    })
    response = client.get(url)
    assert response.status_code == 401
    client.login(user1)
    response = client.get(url)
    assert response.status_code == 200
    client.login(user2)
    response = client.get(url)
    assert response.status_code == 403
    resolver = lms_resolver(url)
    assert issubclass(resolver.func.view_class, RolePermissionRequiredMixin)
    assert resolver.func.view_class.permission_classes == [ViewAccountConnectedServiceProvider]


@pytest.mark.django_db
def test_view_submission_form(client, program_run_cub, program_run_nup):
    submission_form = SubmissionFormFactory(academic_program_run=program_run_cub)
    url = reverse('student_addition', args=(submission_form.id,))
    response = client.get(url)
    assert response.status_code == 200
    assert isinstance(response.context['form'], StudentCreationForm)
    form_data = factory.build(dict, FACTORY_CLASS=UserFactory)
    form_data['terms_accepted'] = True
    form_data['student_id'] = 'cub-id'
    form_data['password1'] = form_data['password2'] = form_data['password']
    response = client.post(url, form_data)
    assert response.status_code == 302

    user = User.objects.get(username=form_data['username'])
    assert user
    user.raw_password = form_data['password']

    profiles = StudentProfile.objects.filter(user=user).all()
    assert len(profiles) == 1
    assert profiles[0].academic_program_enrollment == program_run_cub
    assert profiles[0].student_id == form_data['student_id']

    client.login(user)

    # Duplicate profiles should not be created
    response = client.get(url)
    assert response.status_code == 302
    response = client.post(url, form_data)
    assert response.status_code == 302
    assert StudentProfile.objects.filter(user=user).count() == 1

    # Enrollment to another program
    submission_form = SubmissionFormFactory(academic_program_run=program_run_nup)
    url = reverse('student_addition', args=(submission_form.id,))
    response = client.get(url)
    assert response.status_code == 200
    assert isinstance(response.context['form'], StudentEnrollmentForm)
    form_data_nup = {'student_id': 'nup-id'}
    response = client.post(url, form_data_nup)
    assert response.status_code == 302

    profiles = StudentProfile.objects.filter(user=user).order_by('id').all()
    assert len(profiles) == 2
    cub_profile, nup_profile = profiles
    assert cub_profile.academic_program_enrollment == program_run_cub
    assert nup_profile.academic_program_enrollment == program_run_nup
    assert cub_profile.student_id == form_data['student_id']
    assert nup_profile.student_id == form_data_nup['student_id']


@pytest.mark.django_db
def test_view_submission_form_no_student_id(client, program_run_cub, program_run_nup):
    submission_form = SubmissionFormFactory(
        academic_program_run=program_run_cub,
        require_student_id=False,
    )
    url = reverse('student_addition', args=(submission_form.id,))
    form_data = factory.build(dict, FACTORY_CLASS=UserFactory)
    form_data['terms_accepted'] = True
    form_data['password1'] = form_data['password2'] = form_data['password']
    # Check that student_id input is rendered as hidden
    response = client.get(url)
    assert b'<input type="hidden" name="student_id"' in response.content
    response = client.post(url, form_data)
    assert response.status_code == 302

    user = User.objects.get(username=form_data['username'])
    assert user
    user.raw_password = form_data['password']

    profiles = StudentProfile.objects.filter(user=user).all()
    assert len(profiles) == 1
    assert profiles[0].academic_program_enrollment == program_run_cub
    assert profiles[0].student_id == ''

    client.login(user)

    # Enrollment to another program
    submission_form = SubmissionFormFactory(
        academic_program_run=program_run_nup,
        require_student_id=False,
    )
    url = reverse('student_addition', args=(submission_form.id,))
    # Check that student_id input is rendered as hidden
    response = client.get(url)
    assert b'<input type="hidden" name="student_id"' in response.content
    response = client.post(url, {})
    assert response.status_code == 302

    profiles = StudentProfile.objects.filter(user=user).order_by('id').all()
    assert len(profiles) == 2
    cub_profile, nup_profile = profiles
    assert cub_profile.academic_program_enrollment == program_run_cub
    assert nup_profile.academic_program_enrollment == program_run_nup
    assert cub_profile.student_id == ''
    assert nup_profile.student_id == ''


@pytest.mark.django_db
def test_view_student_id_update_permissions(client):
    profile1 = StudentProfileFactory()
    profile2 = StudentProfileFactory()
    curator = CuratorFactory()
    url = reverse('api:student_id_update', kwargs={'student_profile_id': profile1.pk})
    payload = {'student_id': '1874'}
    response = client.post(url, payload)
    assert response.status_code == 403
    client.login(profile1.user)
    response = client.post(url, payload)
    assert response.status_code == 204
    client.login(profile2.user)
    response = client.post(url, payload)
    assert response.status_code == 403
    client.login(curator)
    response = client.post(url, payload)
    assert response.status_code == 204
