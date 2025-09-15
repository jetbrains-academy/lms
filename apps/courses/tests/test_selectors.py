import pytest

from core.tests.factories import AcademicProgramFactory
from core.tests.settings import TEST_DOMAIN_ID
from courses.tests.factories import CourseClassFactory, CourseFactory, CourseProgramBindingFactory
from learning.selectors import get_classes, get_teacher_classes
from users.tests.factories import TeacherFactory


@pytest.mark.django_db
def test_get_teacher_classes_should_not_return_duplicate_classes(settings):
    t = TeacherFactory(required_groups__site_id=TEST_DOMAIN_ID)
    course = CourseFactory(teachers=[t])
    cc = CourseClassFactory(course=course)
    assert len(get_teacher_classes(t)) == 1


@pytest.mark.django_db
def test_get_classes_should_not_return_duplicate_classes():
    program1, program2 = AcademicProgramFactory.create_batch(2)
    course = CourseFactory()
    for program in [program1, program2]:
        CourseProgramBindingFactory(course=course, program=program)
    assert len(course.programs.all()) == 2
    cc = CourseClassFactory(course=course)
    assert len(get_classes().in_programs([program1])) == 1
    assert len(get_classes().in_programs([program2])) == 1
    assert len(get_classes().in_programs([program1, program2])) == 1
