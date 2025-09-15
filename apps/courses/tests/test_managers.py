import datetime

import pytest

from core.tests.factories import AcademicProgramFactory
from courses.models import CourseClass
from courses.tests.factories import CourseClassFactory, CourseFactory, CourseProgramBindingFactory


@pytest.mark.django_db
def test_course_class_manager(program_cub001, program_nup001):
    program_xxx = AcademicProgramFactory()
    course = CourseFactory()
    for program in [program_cub001, program_nup001, program_xxx]:
        CourseProgramBindingFactory(program=program, course=course)
    cc1 = CourseClassFactory(course=course)
    assert CourseClass.objects.in_programs([program_cub001]).count() == 1
    course2 = CourseProgramBindingFactory(program=program_nup001).course
    assert course2.pk > course.pk
    cc2 = CourseClassFactory(course=course2)

    # Course2 was not shared with CUB program yet
    assert CourseClass.objects.in_programs([program_cub001]).count() == 1

    # Share course2 with CUB program
    CourseProgramBindingFactory(program=program_cub001, course=course2)
    assert CourseClass.objects.in_programs([program_cub001]).count() == 2

    # No duplicates
    classes = list(CourseClass.objects.in_programs([program_cub001, program_nup001]))
    assert len(classes) == 2


@pytest.mark.django_db
def test_course_class_manager_sort_order(program_cub001, program_nup001):
    course1 = CourseProgramBindingFactory(program=program_cub001).course
    course2 = CourseProgramBindingFactory(program=program_cub001).course
    date_on = datetime.date(year=2018, month=1, day=1)
    starts_at = datetime.time(hour=12, minute=0)
    cc1 = CourseClassFactory(course=course1, date=date_on, starts_at=starts_at)
    cc2 = CourseClassFactory(course=course2,
                             date=date_on + datetime.timedelta(days=1),
                             starts_at=starts_at)
    assert CourseClass.objects.in_programs([program_cub001]).count() == 2
    classes = list(CourseClass.objects.in_programs([program_cub001]))
    # Course classes are sorted by date DESC, course ASC, starts_at DESC (see CourseClass.Meta)
    # So cc2 should be the first class in the list
    assert classes[0] == cc2
    assert classes[1] == cc1


