from urllib.parse import urlencode

import pytest
from django.utils import timezone

from alumni.services import promote_to_alumni
from core.urls import reverse
from users.models import User, StudentProfile, AlumniConsent, StudentTypes
from users.tests.factories import StudentFactory, StudentProfileFactory


@pytest.mark.django_db
def test_alumni_list(client, curator):
    list_url = reverse('alumni:list')
    api_list_url = reverse('alumni:api:list')
    current_year = timezone.now().year

    program_title = 'Program A'
    user: User = StudentFactory(
        last_name='Student A',
        student_profile__academic_program_enrollment__program__title=program_title,
        student_profile__year_of_admission=2024,
    )
    sp: StudentProfile = user.get_student_profile()
    invited_profile = StudentProfile(user=user, type=StudentTypes.INVITED)
    promote_to_alumni(sp)
    ap: StudentProfile = user.get_student_profile()
    ap.alumni_consent = AlumniConsent.DECLINED
    ap.save()

    other_program_title = 'Program A'
    other_user: User = StudentFactory(
        last_name='Student B',
        student_profile__academic_program_enrollment__program__title=other_program_title,
        student_profile__year_of_admission=2024,
    )
    other_sp: StudentProfile = other_user.get_student_profile()
    promote_to_alumni(other_sp)
    other_ap: StudentProfile = other_user.get_student_profile()

    non_graduated = StudentFactory()
    non_graduated_invited = StudentFactory(student_profile__type=StudentTypes.INVITED)

    client.login(user)

    resp = client.get(list_url)
    assert resp.status_code == 200
    assert resp.context_data['react_data']['programs'] == [
        {
            'program_id': sp.academic_program_enrollment.program.id,
            'program_title': program_title,
            'graduation_year': current_year,
        },
        {
            'program_id': other_sp.academic_program_enrollment.program.id,
            'program_title': other_program_title,
            'graduation_year': current_year,
        },
    ]

    resp = client.get(api_list_url)
    assert resp.status_code == 200
    resp_data = resp.json()
    # Consent not given
    assert len(resp_data['alumni']) == 0

    # Curator can see all alumni regardless of the consent status
    client.login(curator)
    resp = client.get(api_list_url)
    assert resp.status_code == 200
    resp_data = resp.json()
    assert len(resp_data['alumni']) == 2
    client.login(user)

    ap.alumni_consent = AlumniConsent.ACCEPTED
    ap.save()

    resp = client.get(api_list_url)
    assert resp.status_code == 200
    resp_data = resp.json()
    # 1 user gave consent
    assert len(resp_data['alumni']) == 1
    assert resp_data['alumni'][0]['id'] == user.id
    assert len(resp_data['alumni'][0]['graduations']) == 1
    assert (
        resp_data['alumni'][0]['graduations'][0]['program_id']
        == sp.academic_program_enrollment.program.id
    )

    other_ap.alumni_consent = AlumniConsent.ACCEPTED
    other_ap.save()

    resp = client.get(api_list_url)
    assert resp.status_code == 200
    resp_data = resp.json()
    # 2 users gave consent
    assert len(resp_data['alumni']) == 2
    assert resp_data['alumni'][0]['id'] == user.id
    assert resp_data['alumni'][1]['id'] == other_user.id
    assert len(resp_data['alumni'][0]['graduations']) == 1
    assert len(resp_data['alumni'][1]['graduations']) == 1
    assert (
        resp_data['alumni'][0]['graduations'][0]['program_id']
        == sp.academic_program_enrollment.program.id
    )
    assert (
        resp_data['alumni'][1]['graduations'][0]['program_id']
        == other_sp.academic_program_enrollment.program.id
    )

    # Check that all graduations are displayed
    sp2: StudentProfile = StudentProfileFactory(user=user, year_of_admission=2025)
    promote_to_alumni(sp2)

    resp = client.get(api_list_url)
    assert resp.status_code == 200
    resp_data = resp.json()
    # 2 users gave consent
    assert len(resp_data['alumni']) == 2
    assert resp_data['alumni'][0]['id'] == user.id
    assert len(resp_data['alumni'][0]['graduations']) == 2
    assert (
        resp_data['alumni'][0]['graduations'][0]['program_id']
        == sp.academic_program_enrollment.program.id
    )
    assert (
        resp_data['alumni'][0]['graduations'][1]['program_id']
        == sp2.academic_program_enrollment.program.id
    )


@pytest.mark.django_db
def test_alumni_list_filters(client):
    api_list_url = reverse('alumni:api:list')
    current_year = timezone.now().year

    user: User = StudentFactory()
    sp: StudentProfile = user.get_student_profile()
    promote_to_alumni(sp)
    ap: StudentProfile = user.get_student_profile()
    ap.alumni_consent = AlumniConsent.ACCEPTED
    ap.save()

    other_user: User = StudentFactory()
    other_sp: StudentProfile = other_user.get_student_profile()
    promote_to_alumni(other_sp)
    other_ap: StudentProfile = other_user.get_student_profile()
    other_ap.alumni_consent = AlumniConsent.ACCEPTED
    other_ap.save()

    client.login(user)

    def search(
        *,
        program: int | None = None,
        graduation_year: int | None = None,
        expected_status: int = 200,
        expected_users: set[int] | None = None,
    ):
        query = {'program': program, 'graduation_year': graduation_year}
        resp = client.get(api_list_url + '?' + urlencode(query))
        if expected_status == 200:
            assert resp.status_code == 200
            resp_data = resp.json()
            assert len(resp_data['alumni']) == len(expected_users)
            assert {x['id'] for x in resp_data['alumni']} == expected_users
        else:
            if expected_users is not None:
                raise ValueError(
                    "expected_users can't be passed together with expected_status"
                )
            assert resp.status_code == expected_status

    search(
        program=sp.academic_program_enrollment.program.id,
        graduation_year=current_year,
        expected_users={user.id},
    )
    search(
        program=other_sp.academic_program_enrollment.program.id,
        graduation_year=current_year,
        expected_users={other_user.id},
    )
    search(
        program=-1,
        graduation_year=current_year,
        expected_status=400,
    )
    search(
        program=None,
        graduation_year=current_year,
        expected_status=400,
    )
    search(
        program=sp.academic_program_enrollment.program.id,
        graduation_year=None,
        expected_status=400,
    )


@pytest.mark.django_db
def test_alumni_promote_view(client, curator):
    api_promote_url = reverse('alumni:api:promote')
    sp: StudentProfile = StudentProfileFactory()
    user = sp.user
    sp2: StudentProfile = StudentProfileFactory()
    user2 = sp2.user
    client.login(curator)
    resp = client.post(
        api_promote_url,
        {'student_profiles': [sp.id, sp2.id]},
        content_type='application/json',
    )
    assert resp.status_code == 204
    assert user.get_student_profile().type == StudentTypes.ALUMNI
    assert user2.get_student_profile().type == StudentTypes.ALUMNI


@pytest.mark.django_db
def test_alumni_consent_form(client, assert_redirect):
    list_url = reverse('alumni:list')
    consent_form_url = reverse('alumni:consent_form')

    sp: StudentProfile = StudentProfileFactory()
    user = sp.user
    promote_to_alumni(sp)
    ap: StudentProfile = user.get_student_profile()
    client.login(user)

    # Shouldn't allow to view list page before accepting/rejecting the form
    assert_redirect(client.get(list_url), consent_form_url)

    resp = client.post(
        consent_form_url,
        {
            'consent': False,
        },
    )
    assert_redirect(resp, list_url)
    ap.refresh_from_db()
    assert ap.alumni_consent == AlumniConsent.DECLINED
    # Should now allow to view list
    assert client.get(list_url).status_code == 200

    resp = client.post(
        consent_form_url,
        {
            'consent': True,
        },
    )
    assert_redirect(resp, list_url)
    ap.refresh_from_db()
    assert ap.alumni_consent == AlumniConsent.ACCEPTED
    assert client.get(list_url).status_code == 200


@pytest.mark.django_db
def test_alumni_consent_in_user_profile(client):
    sp: StudentProfile = StudentProfileFactory()
    user = sp.user
    client.login(user)
    update_profile_url = user.get_update_profile_url()

    resp = client.get(update_profile_url)
    assert b'alumni_consent' not in resp.content

    promote_to_alumni(sp)
    ap: StudentProfile = user.get_student_profile()

    resp = client.get(update_profile_url)
    assert b'alumni_consent' in resp.content
    resp = client.post(update_profile_url, {
        'time_zone': user.time_zone,
        'alumni_consent': True
    })
    assert resp.status_code == 302
    ap.refresh_from_db()
    assert ap.alumni_consent == AlumniConsent.ACCEPTED
