import pytest
from django.contrib.sites.models import Site
from pandas import DataFrame

from core.tests.factories import SiteFactory
from courses.tests.factories import MetaCourseFactory
from learning.reports import ProgressReportForSemester, ProgressReportFull
from learning.settings import GradeTypes
from learning.tests.factories import CourseFactory, EnrollmentFactory, SemesterFactory
from users.tests.factories import StudentFactory, TeacherFactory


def check_value_for_header(report, header, row_index, expected_value):
    assert header in report.columns
    assert report.loc[row_index, header] == expected_value


@pytest.mark.django_db
def test_report_common(settings):
    def get_progress_report():
        return ProgressReportFull().generate()

    STATIC_HEADERS_CNT = len(get_progress_report().columns)

    teacher = TeacherFactory.create()
    s = SemesterFactory.create_current()
    co1, co2, co3 = CourseFactory.create_batch(3, semester=s,
                                               teachers=[teacher])
    student1, student2, student3 = StudentFactory.create_batch(3)
    EnrollmentFactory(student=student1, course=co1, grade=4)
    EnrollmentFactory(student=student2, course=co1, grade=4)
    EnrollmentFactory(student=student2, course=co2, grade=GradeTypes.NOT_GRADED)

    # generate club course
    site_club = SiteFactory(domain=Site.objects.get(id=1))
    course_club = CourseFactory()
    EnrollmentFactory(student=student1, course=course_club, grade=4)

    report_factory = ProgressReportFull()
    progress_report = report_factory.generate()
    assert len(progress_report.columns) == (
        STATIC_HEADERS_CNT +
        len({c.meta_course_id: c.meta_course for c in (co1, co2, course_club)})
    )

    assert progress_report.index[0] == student1.pk
    assert progress_report.index[1] == student2.pk
    assert progress_report.index[2] == student3.pk


@pytest.mark.django_db
def test_report_for_target_term():
    def get_progress_report(term) -> DataFrame:
        return ProgressReportForSemester(term).generate()

    teacher = TeacherFactory.create()
    current_term = SemesterFactory.create_current()
    prev_term = SemesterFactory.create_prev(current_term)
    STATIC_HEADERS_CNT = len(get_progress_report(current_term).columns)
    co_active = CourseFactory.create(semester=current_term, teachers=[teacher])
    co1, co2, co3 = CourseFactory.create_batch(3, semester=prev_term,
                                               teachers=[teacher])
    student1, student2, student3 = StudentFactory.create_batch(3)
    e_active = EnrollmentFactory.create(student=student1,
                                        course=co_active,
                                        grade=5)
    e_active2 = EnrollmentFactory.create(student=student2,
                                         course=co_active,
                                         grade=GradeTypes.NOT_GRADED)
    e_old1 = EnrollmentFactory.create(student=student1, course=co1,
                                      grade=4)
    e_old2 = EnrollmentFactory.create(student=student2, course=co1,
                                      grade=GradeTypes.NOT_GRADED)
    active_courses_count = 1
    prev_courses_count = 1
    progress_report = get_progress_report(prev_term)
    assert len(progress_report) == 3
    # FIXME: add status for graduate first
    # Graduated students not included in report
    # student3.groups.all().delete()
    # student3.add_group(Roles.GRADUATE)
    # progress_report = get_progress_report(prev_term)
    # assert len(progress_report) == 2
    # `co_active` headers not in report for passed terms
    assert len(progress_report.columns) == (STATIC_HEADERS_CNT +
                                            prev_courses_count)
    assert co_active.meta_course.name not in progress_report.columns
    # Check `not_graded` values included for passed target term
    student1_data_index = 0
    student2_data_index = 1
    assert progress_report.index[student2_data_index] == student2.pk
    course_header_grade = co1.meta_course.name
    check_value_for_header(progress_report, course_header_grade,
                           student2.pk, e_old2.grade_display.lower())
    # And included for current target term. Compare expected value with actual
    progress_report = get_progress_report(current_term)
    assert len(progress_report.columns) == (STATIC_HEADERS_CNT +
                                            active_courses_count)
    course_header_grade = co_active.meta_course.name
    assert progress_report.index[student1_data_index] == student1.pk
    check_value_for_header(progress_report, course_header_grade,
                           student1.pk, e_active.grade_display.lower())
    assert progress_report.index[student2_data_index] == student2.pk
    check_value_for_header(progress_report, course_header_grade,
                           student2.pk, e_active2.grade_display.lower())
    # Check honest grade system
    e = EnrollmentFactory.create(student=student1, course=co2,
                                 grade=3)
    progress_report = get_progress_report(prev_term)
    assert progress_report.index[student1_data_index] == student1.pk
    course_header_grade = co2.meta_course.name
    check_value_for_header(progress_report, course_header_grade,
                           student1.pk, e.grade_display.lower())
    # Test `success_total_lt_target_semester` value
    success_total_lt_ts_header = (
        'Successful enrollments before "%s"' % prev_term)
    success_total_eq_ts_header = (
        'Successful enrollments in "%s"' % prev_term)
    # +2 successful enrollments
    check_value_for_header(progress_report, success_total_lt_ts_header,
                           student1.pk, 0)
    check_value_for_header(progress_report, success_total_eq_ts_header,
                           student1.pk, 2)
    # And 1 successful enrollment in current semester
    progress_report = get_progress_report(current_term)
    success_total_lt_ts_header = (
        'Successful enrollments before "%s"' % current_term)
    success_total_eq_ts_header = (
        'Successful enrollments in "%s"' % current_term)
    check_value_for_header(progress_report, success_total_lt_ts_header,
                           student1.pk, 2)
    check_value_for_header(progress_report, success_total_eq_ts_header,
                           student1.pk, 1)
    # TODO: Test enrollments_in_target_semester


@pytest.mark.django_db
def test_export_highest_or_max_grade(settings):
    report = ProgressReportFull(on_course_duplicate='store_max')
    student = StudentFactory()
    meta_course = MetaCourseFactory()
    term_current = SemesterFactory.create_current()
    term_prev = SemesterFactory.create_prev(term_current)
    term_prev2 = SemesterFactory.create_prev(term_prev)
    course1 = CourseFactory(meta_course=meta_course, semester=term_prev2)
    course2 = CourseFactory(meta_course=meta_course, semester=term_prev)
    course3 = CourseFactory(meta_course=meta_course, semester=term_current)
    EnrollmentFactory(student=student, course=course1, grade=5)
    EnrollmentFactory(student=student, course=course2, grade=4)
    EnrollmentFactory(student=student, course=course3, grade=GradeTypes.NOT_GRADED)
    df = report.generate()
    assert df[meta_course.name].iloc[0] == '5'
    df = ProgressReportFull(on_course_duplicate='store_last').generate()
    assert df[meta_course.name].iloc[0] == '4'
