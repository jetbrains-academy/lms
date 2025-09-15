from itertools import chain

import pytest
from django.contrib.sites.models import Site
from icalendar import Calendar, Event

from core.urls import reverse
from courses.tests.factories import AssignmentFactory, CourseClassFactory, CourseFactory
from learning.tests.factories import EnrollmentFactory, EventFactory
from users.constants import Roles
from users.tests.factories import StudentFactory


# TODO: ensure that timezone for assignments/classes is taken from calendar URL user timezone, not from logged in user
# TODO: for events - use logged in user timezone for now


@pytest.mark.django_db
def test_smoke(client, curator, settings):
    """Any user can view icalendar since these urls are not secret"""
    student = StudentFactory()
    response = client.get(student.get_classes_icalendar_url())
    assert response.status_code == 200
    response = client.get(student.get_assignments_icalendar_url())
    assert response.status_code == 200


@pytest.mark.django_db
def test_course_classes(client, settings, mocker):
    user = StudentFactory(groups=[Roles.TEACHER])
    client.login(user)
    fname = 'classes.ics'
    # Empty calendar
    response = client.get(user.get_classes_icalendar_url())
    assert response['content-type'] == "text/calendar; charset=UTF-8"
    assert fname in response['content-disposition']
    cal = Calendar.from_ical(response.content)
    site = Site.objects.get(pk=settings.SITE_ID)
    assert f"Classes {site.name}" == cal['X-WR-CALNAME']
    # Create some content
    ccs_teaching = (CourseClassFactory
                    .create_batch(2, course__teachers=[user]))
    course = CourseFactory.create()
    EnrollmentFactory.create(student=user, course=course)
    ccs_learning = (CourseClassFactory
                    .create_batch(3, course=course))
    ccs_other = CourseClassFactory.create_batch(5)
    response = client.get(user.get_classes_icalendar_url())
    cal = Calendar.from_ical(response.content)
    cal_events = {evt['SUMMARY'] for evt in
                  cal.subcomponents if isinstance(evt, Event)}
    for cc in ccs_learning:
        assert cc.name in cal_events
    for cc in ccs_teaching:
        assert cc.name in cal_events


@pytest.mark.django_db
def test_assignments(client, settings, mocker):
    user = StudentFactory(groups=[Roles.TEACHER])
    client.login(user)
    fname = 'assignments.ics'
    # Empty calendar
    resp = client.get(user.get_assignments_icalendar_url())
    assert "text/calendar; charset=UTF-8" == resp['content-type']
    assert fname in resp['content-disposition']
    cal = Calendar.from_ical(resp.content)
    site = Site.objects.get(pk=settings.SITE_ID)
    assert f"Assignments {site.name}" == cal['X-WR-CALNAME']
    # Create some content
    as_teaching = (AssignmentFactory
                   .create_batch(2, course__teachers=[user]))
    co_learning = CourseFactory.create()
    EnrollmentFactory.create(student=user, course=co_learning)
    as_learning = (AssignmentFactory
                   .create_batch(3, course=co_learning))
    as_other = AssignmentFactory.create_batch(5)
    resp = client.get(user.get_assignments_icalendar_url())
    cal = Calendar.from_ical(resp.content)
    assert {f"{a.title} ({a.course.meta_course.name})" for a in
            chain(as_teaching, as_learning)} == {
               evt['SUMMARY'] for evt in cal.subcomponents if isinstance(evt, Event)}


@pytest.mark.django_db
def test_events(client, settings):
    file_name = 'events.ics'
    url = reverse('ical_events', subdomain=settings.LMS_SUBDOMAIN)
    # Empty calendar
    response = client.get(url)
    assert "text/calendar; charset=UTF-8" == response['content-type']
    assert file_name in response['content-disposition']
    cal = Calendar.from_ical(response.content)
    site = Site.objects.get(pk=settings.SITE_ID)
    assert f"Events {site.name}" == cal['X-WR-CALNAME']
    # Create some content
    nces = EventFactory.create_batch(3)
    response = client.get(url)
    cal = Calendar.from_ical(response.content)
    assert set(nce.name for nce in nces) == set(evt['SUMMARY']
                                                for evt in cal.subcomponents
                                                if isinstance(evt, Event))
