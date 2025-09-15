import pytest

from courses.tests.factories import CourseFactory, CourseProgramBindingFactory
from learning.models import Enrollment
from learning.settings import GradeTypes, GradingSystems
from learning.tests.factories import EnrollmentFactory
from users.tests.factories import StudentProfileFactory


def test_get_choices_for_grading_system():
    grades = dict(GradeTypes.get_choices_for_grading_system(GradingSystems.FIVE_POINT))
    assert GradeTypes.RE_CREDIT in grades
    assert GradeTypes.NOT_GRADED in grades
    assert 5 in grades
    assert 10 not in grades
    grades = dict(GradeTypes.get_choices_for_grading_system(GradingSystems.BINARY))
    assert GradeTypes.RE_CREDIT in grades
    assert GradeTypes.NOT_GRADED in grades
    assert GradeTypes.EXCELLENT not in grades
    assert GradeTypes.PASS in grades
    grades = dict(GradeTypes.get_choices_for_grading_system(GradingSystems.TEN_POINT))
    assert GradeTypes.RE_CREDIT in grades
    assert GradeTypes.NOT_GRADED in grades
    assert 10 in grades
    assert 100 not in grades
    grades = dict(GradeTypes.get_choices_for_grading_system(GradingSystems.HUNDRED_POINT))
    assert GradeTypes.RE_CREDIT in grades
    assert GradeTypes.NOT_GRADED in grades
    assert 10 in grades
    assert 100 in grades


@pytest.mark.django_db
@pytest.mark.parametrize(
    'grading_system,failing_grades,passing_grades',
    [
        (
            GradingSystems.BINARY,
            (GradeTypes.NOT_GRADED, GradeTypes.RE_CREDIT, GradeTypes.FAIL),
            (GradeTypes.PASS,),
        ),
        (
            GradingSystems.BINARY_PLUS_EXCELLENT,
            (GradeTypes.NOT_GRADED, GradeTypes.RE_CREDIT, GradeTypes.FAIL),
            (GradeTypes.PASS, GradeTypes.EXCELLENT),
        ),
        (
            GradingSystems.FIVE_POINT,
            (GradeTypes.NOT_GRADED, GradeTypes.RE_CREDIT, 1, 2),
            (3, 4, 5),
        ),
        (
            GradingSystems.TEN_POINT,
            (GradeTypes.NOT_GRADED, GradeTypes.RE_CREDIT, 1, 3),
            (4, 5, 10),
        ),
        (
            GradingSystems.HUNDRED_POINT,
            (GradeTypes.NOT_GRADED, GradeTypes.RE_CREDIT, 1, 5, 10, 44),
            (45, 100),
        ),
    ],
)
def test_passing_grade_expr(grading_system, passing_grades, failing_grades, program_cub001, program_run_cub):
    student_profile = StudentProfileFactory(academic_program_enrollment=program_run_cub)
    for grade in failing_grades + passing_grades:
        cpb = CourseProgramBindingFactory.create(program=program_cub001, grading_system_num=grading_system)
        EnrollmentFactory.create(
            student=student_profile.user,
            course=cpb.course,
            course_program_binding=cpb,
            grade=grade
        )
    failing_enrollments = Enrollment.objects.filter(grade__lt=GradingSystems.get_passing_grade_expr()).all()
    passing_enrollments = Enrollment.objects.filter(grade__gte=GradingSystems.get_passing_grade_expr()).all()
    assert len(failing_enrollments) == len(failing_grades)
    assert {x.grade for x in failing_enrollments} == set(failing_grades)
    assert len(passing_enrollments) == len(passing_grades)
    assert {x.grade for x in passing_enrollments} == set(passing_grades)


@pytest.mark.django_db
def test_passing_grade_expr_mixed_grading_systems(program_cub001, program_run_cub):
    student_profile = StudentProfileFactory(academic_program_enrollment=program_run_cub)
    cpb = CourseProgramBindingFactory.create(
        program=program_cub001, grading_system_num=GradingSystems.FIVE_POINT
    )
    EnrollmentFactory.create(student=student_profile.user, course=cpb.course, course_program_binding=cpb, grade=4)
    cpb = CourseProgramBindingFactory.create(
        program=program_cub001, grading_system_num=GradingSystems.TEN_POINT
    )
    EnrollmentFactory.create(student=student_profile.user, course=cpb.course, course_program_binding=cpb, grade=4)
    cpb = CourseProgramBindingFactory.create(
        program=program_cub001, grading_system_num=GradingSystems.HUNDRED_POINT
    )
    EnrollmentFactory.create(student=student_profile.user, course=cpb.course, course_program_binding=cpb, grade=4)

    failing_enrollments = Enrollment.objects.filter(grade__lt=GradingSystems.get_passing_grade_expr()).all()
    passing_enrollments = Enrollment.objects.filter(grade__gte=GradingSystems.get_passing_grade_expr()).all()
    assert len(failing_enrollments) == 1
    assert len(passing_enrollments) == 2
