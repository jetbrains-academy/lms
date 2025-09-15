import pytest
from bs4 import BeautifulSoup
from django.forms import inlineformset_factory

from courses.admin import CourseTeacherInline
from courses.constants import AssigneeMode, AssignmentFormat
from courses.models import (
    Assignment, Course, CourseTeacher
)
from courses.tests.factories import CourseFactory
from users.tests.factories import CuratorFactory, TeacherFactory


def _get_course_teachers_post_data(course=None):
    """Returns POST-data for inline formset"""
    prefix = 'course_teachers'
    if course is not None:
        course_teachers = CourseTeacher.objects.filter(course=course)
        initial_forms = len(course_teachers)
    else:
        initial_forms = 0
        teacher = TeacherFactory()
        course_teachers = [CourseTeacher(teacher=teacher,
                                         course=course,
                                         roles=CourseTeacher.roles.lecturer)]
    form_data = {
        f'{prefix}-INITIAL_FORMS': initial_forms,
        f'{prefix}-MIN_NUM_FORMS': 1,
        f'{prefix}-TOTAL_FORMS': len(course_teachers),
        f'{prefix}-MAX_NUM_FORMS': 1000,
    }
    for i, course_teacher in enumerate(course_teachers):
        roles = [v for v, has_role in course_teacher.roles.items() if has_role]
        data = {
            f'{prefix}-{i}-teacher': course_teacher.teacher_id,
            f'{prefix}-{i}-roles': roles,
            f'{prefix}-{i}-notify_by_default': course_teacher.notify_by_default,
        }
        if course is not None:
            data[f'{prefix}-{i}-id'] = course_teacher.pk
            data[f'{prefix}-{i}-course'] = course.pk
        form_data.update(data)
    return form_data


@pytest.mark.django_db
def test_course_teacher_inline_formset():
    teacher = TeacherFactory()
    CourseTeacherInlineFormSet = inlineformset_factory(
        Course, CourseTeacher, formset=CourseTeacherInline.formset,
        fields=['teacher', 'roles', 'notify_by_default'])
    data = {
        'course_teachers-INITIAL_FORMS': 0,
        'course_teachers-MIN_NUM_FORMS': 1,
        'course_teachers-MAX_NUM_FORMS': 1000,
        'course_teachers-TOTAL_FORMS': 1,
        'course_teachers-0-teacher': teacher.pk,
        'course_teachers-0-roles': ['lecturer'],
    }
    form_set = CourseTeacherInlineFormSet(data, instance=CourseFactory())
    assert form_set.is_valid()
    course = CourseFactory()
    data = _get_course_teachers_post_data(course)
    form_set = CourseTeacherInlineFormSet(data, instance=course)
    assert form_set.is_valid()


@pytest.mark.django_db
def test_assignment_admin_view(settings, client):
    curator = CuratorFactory()
    client.login(curator)
    # Datetime widget formatting depends on locale, change it
    settings.LANGUAGE_CODE = 'ru'

    co_in_spb = CourseFactory()
    form_data = {
        "assignment-assignee_mode": AssigneeMode.STUDENT_GROUP_DEFAULT,
        "assignment-submission_type": AssignmentFormat.ONLINE,
        "assignment-opens_at_0": "29.06.2010",
        "assignment-opens_at_1": "00:00",
        "assignment-deadline_at_0": "29.06.2017",
        "assignment-deadline_at_1": "00:00",
        "assignment-time_zone": "UTC",
        "assignment-title": "title",
        "assignment-text": "text",
        "assignment-maximum_score": "5",
        "assignment-weight": "1.00",
    }
    # Send valid data
    add_url = co_in_spb.get_create_assignment_url()
    response = client.post(add_url, form_data)
    assert response.status_code == 302
    assert Assignment.objects.count() == 1
    assignment = Assignment.objects.first()
    # In SPB we have msk timezone (UTC +3)
    # In DB we store datetime values in UTC
    assert assignment.deadline_at.day == 29
    assert assignment.deadline_at.hour == 0
    assert assignment.deadline_at.minute == 0
    # Admin widget shows localized time
    edit_url = assignment.get_update_url()

    def get_datetime_inputs():
        response = client.get(edit_url)
        update_form = response.context['assignment_form']
        widget_html = update_form['deadline_at'].as_widget()
        widget = BeautifulSoup(widget_html, "html.parser")
        date_input = widget.find('input', {"name": 'assignment-deadline_at_0'})
        time_input = widget.find('input', {"name": 'assignment-deadline_at_1'})
        return date_input, time_input

    date_input, time_input = get_datetime_inputs()
    assert time_input.get('value') == '00:00'
    assert date_input.get('value') == '29.06.2017'
    # Update the deadline time
    form_data["assignment-deadline_at_1"] = "06:00"
    response = client.post(edit_url, form_data)
    assert response.status_code == 302
    assignment.refresh_from_db()
    _, time_input = get_datetime_inputs()
    assert time_input.get('value') == '06:00'
    assert assignment.deadline_at.hour == 6
    assert assignment.deadline_at.minute == 0
