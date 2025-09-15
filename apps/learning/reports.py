from abc import ABCMeta, abstractmethod
from enum import Enum
from typing import Dict, List, Literal, Set

from django.db.models import Case, Count, F, IntegerField, Prefetch, Q, When
from pandas import DataFrame

from courses.constants import SemesterTypes
from courses.models import Course, MetaCourse
from courses.selectors import course_teachers_prefetch_queryset
from courses.utils import get_term_index
from learning.models import Enrollment
from learning.settings import StudentStatuses, GradingSystems
from users.managers import get_enrollments_progress
from users.models import StudentProfile, StudentTypes, User


class ReportColumn(str, Enum):
    ID = 'ID'
    FIRST_NAME = 'First Name'
    LAST_NAME = 'Last Name'
    GENDER = 'Gender'
    PHONE = 'Phone'
    EMAIL = 'Email'
    TELEGRAM = 'Telegram'
    WORKPLACE = 'Workplace'
    DATE_OF_BIRTH = 'Date of Birth'
    GITHUB = 'Github'
    CODEFORCES = 'Codeforces'
    COGNITERRA = 'Cogniterra'
    JETBRAINS = 'JetBrains account'
    LINKEDIN = 'LinkedIn'

    PROGRAM_RUN = 'Program Run'
    STATUS = 'Status'
    STUDENT_ID = 'Student ID'

    UNIVERSITY = 'University'
    YEAR_OF_ADMISSION = 'Year of admission'
    SEMESTER_NUMBER = 'Semester number'
    COMMENT = 'Comment'
    COMMENT_CHANGED_AT = 'Comment changed at'

    SUCCESSFUL_ENROLLMENTS_BEFORE = 'Successful enrollments before "{semester}"'
    SUCCESSFUL_ENROLLMENTS_IN = 'Successful enrollments in "{semester}"'
    ENROLLMENTS_IN = 'Enrollments in "{semester}"'


class ProgressReport:
    """
    Generates report for students course progress.

    Usage example:
        report = ProgressReport()
        custom_queryset = report.get_queryset().filter(pk=404)
        df: pandas.DataFrame = report.generate(custom_queryset)
        # Return response in csv format
        response = DataFrameResponse.as_csv(df, 'report_file.csv')
    """

    __metaclass__ = ABCMeta

    def __init__(
        self,
        on_course_duplicate: Literal["store_last", "store_max"] = "store_last",
    ):
        """
        Two options to choose what grade to export when student take
        a course multiple times:
            *store_last* - grade from the last satisfactory passed course
            *store_max* - the highest grade
        """
        self.on_course_duplicate = on_course_duplicate

    @abstractmethod
    def get_queryset(self):
        return StudentProfile.objects.none()

    @abstractmethod
    def _generate_headers(
        self,
        *,
        meta_courses: dict[int, MetaCourse],
    ) -> list[str]:
        raise NotImplementedError

    @staticmethod
    def _get_course_headers(meta_courses: dict[int, MetaCourse]):
        return [course.name for course in meta_courses.values()]

    @abstractmethod
    def _export_row(
        self,
        student_profile: StudentProfile,
        *,
        meta_courses: dict[int, MetaCourse],
    ) -> list[tuple[str, str]]:
        raise NotImplementedError

    @staticmethod
    def _export_course_grades(student: User, meta_courses_ids: list[int]) -> list[str]:
        values = [""] * len(meta_courses_ids)
        for i, meta_course_id in enumerate(meta_courses_ids):
            if meta_course_id in student.unique_enrollments:
                enrollment = student.unique_enrollments[meta_course_id]
                values[i] = enrollment.grade_display.lower()
        return values

    def get_courses_queryset(self, students):
        courses: Set[int] = set()
        for student in students:
            for e in student.enrollments_progress:
                courses.add(e.course_id)
        course_teachers = Prefetch(
            "course_teachers", queryset=course_teachers_prefetch_queryset()
        )
        qs = (
            Course.objects.filter(pk__in=courses)
            .select_related("meta_course", "semester")
            .only(
                "semester_id",
                "semester__index",
                "meta_course_id",
                "meta_course__name",
                "meta_course__slug"
            )
            .prefetch_related(course_teachers)
        )
        return qs

    def generate(self, queryset=None) -> DataFrame:
        student_profiles = queryset or self.get_queryset()
        # It's possible to prefetch all related courses but nested
        # .prefetch_related() for course teachers is extremely slow
        students = (sp.user for sp in student_profiles)
        unique_courses: Dict[int, Course] = {
            c.pk: c for c in self.get_courses_queryset(students)
        }
        unique_meta_courses: Dict[int, MetaCourse] = {}
        for student_profile in student_profiles:
            student_account = student_profile.user
            self.process_student(student_account, unique_courses, unique_meta_courses)

        # Alphabetically sort meta courses by name
        meta_course_names = [(mc.name, mc.pk) for mc in unique_meta_courses.values()]
        meta_course_names.sort()
        meta_courses: Dict[int, MetaCourse] = {}
        for _, pk in meta_course_names:
            meta_courses[pk] = unique_meta_courses[pk]

        headers = self._generate_headers(
            meta_courses=meta_courses,
        )

        data = []
        for student_profile in student_profiles:
            row = self._export_row(
                student_profile,
                meta_courses=meta_courses,
            )
            curr_headers = [x[0] for x in row]
            if curr_headers != headers:
                raise ValueError('_export_row returned different headers')
            headers = curr_headers
            row_data = [x[1] for x in row]
            data.append(row_data)
        return DataFrame.from_records(columns=headers, data=data, index="ID")

    def process_student(self, student, unique_courses, unique_meta_courses):
        grades: Dict[int, Enrollment] = {}
        for enrollment in student.enrollments_progress:
            self.before_skip_enrollment(enrollment, student, unique_courses)
            if self.skip_enrollment(enrollment, student, unique_courses):
                continue
            course = unique_courses[enrollment.course_id]
            meta_course_id = course.meta_course_id
            unique_meta_courses[meta_course_id] = course.meta_course
            if meta_course_id in grades:
                current_enrollment = grades[meta_course_id]
                # Store the latest satisfactory grade
                if self.on_course_duplicate == "store_last":
                    current_course = unique_courses[current_enrollment.course_id]
                    grading_system = enrollment.course_program_binding.grading_system
                    is_current_grade_satisfactory = (
                        current_enrollment.grade >= grading_system.pass_from
                    )
                    is_grade_satisfactory = (
                        enrollment.grade >= grading_system.pass_from
                    )
                    is_grade_newer = (
                        course.semester.index > current_course.semester.index
                    )
                    if is_grade_satisfactory and (
                        is_grade_newer or not is_current_grade_satisfactory
                    ):
                        grades[meta_course_id] = enrollment
                # Stores the highest grade
                elif self.on_course_duplicate == "store_max":
                    # The behavior is not specified if different grading systems were
                    # used in different terms (e.g. 10-point scale and binary)
                    if enrollment.grade > current_enrollment.grade:
                        grades[meta_course_id] = enrollment
            else:
                grades[meta_course_id] = enrollment
        student.unique_enrollments = grades

    def before_skip_enrollment(self, enrollment, student, courses) -> None:
        """
        Hook for collecting stats. Called before .skip_enrollment method.
        """
        pass

    def skip_enrollment(self, enrollment, student, courses):
        return False


class ProgressReportFull(ProgressReport):
    def get_queryset(self, base_queryset=None):
        enrollments_prefetch = get_enrollments_progress(
            lookup="user__enrollment_set",
        )

        if base_queryset is None:
            base_queryset = (
                StudentProfile.objects.filter(
                    type=StudentTypes.REGULAR,
                )
                .select_related("user")
                .order_by("user__last_name", "user__first_name", "user__pk")
            )
        # Take into account only 1 enrollment if student passed the course twice
        success_enrollments_total = Count(
            Case(
                When(
                    Q(user__enrollment__grade__gte=GradingSystems.get_passing_grade_expr('user__enrollment'))
                    & Q(user__enrollment__is_deleted=False),
                    then=F("user__enrollment__course__meta_course_id"),
                ),
                output_field=IntegerField(),
            ),
            distinct=True,
        )
        return (
            base_queryset.defer(
                "user__private_contacts",
                "user__bio",
            )
            .prefetch_related(enrollments_prefetch)
            .annotate(success_enrollments=success_enrollments_total)
        )

    def _generate_headers(
        self,
        *,
        meta_courses: dict[int, MetaCourse],
    ) -> list[str]:
        return [
            ReportColumn.ID,
            ReportColumn.FIRST_NAME,
            ReportColumn.LAST_NAME,
            ReportColumn.GENDER,
            ReportColumn.PHONE,
            ReportColumn.EMAIL,
            ReportColumn.TELEGRAM,
            ReportColumn.WORKPLACE,
            ReportColumn.DATE_OF_BIRTH,
            ReportColumn.GITHUB,
            ReportColumn.CODEFORCES,
            ReportColumn.COGNITERRA,
            ReportColumn.JETBRAINS,
            ReportColumn.LINKEDIN,

            ReportColumn.PROGRAM_RUN,
            ReportColumn.STATUS,
            ReportColumn.STUDENT_ID,

            *self._get_course_headers(meta_courses),
        ]

    def _export_row(
        self,
        student_profile: StudentProfile,
        *,
        meta_courses: dict[int, MetaCourse],
    ) -> list[tuple[str, str]]:
        student = student_profile.user
        return [
            (ReportColumn.ID, student.pk),
            (ReportColumn.FIRST_NAME, student.first_name),
            (ReportColumn.LAST_NAME, student.last_name),
            (ReportColumn.GENDER, student.get_gender_display()),
            (ReportColumn.PHONE, student.phone),
            (ReportColumn.EMAIL, student.email),
            (ReportColumn.TELEGRAM, student.telegram_username),
            (ReportColumn.WORKPLACE, student.workplace),
            (ReportColumn.DATE_OF_BIRTH, student.birth_date.strftime('%m.%d.%Y') if student.birth_date else '-'),
            (ReportColumn.GITHUB, student.github_login),
            (ReportColumn.CODEFORCES, student.codeforces_login),
            (ReportColumn.COGNITERRA, student.cogniterra_user_id or ''),
            (ReportColumn.JETBRAINS, student.jetbrains_account),
            (ReportColumn.LINKEDIN, student.linkedin_profile),

            (ReportColumn.PROGRAM_RUN, str(student_profile.academic_program_enrollment) if student_profile.academic_program_enrollment else '-'),
            (ReportColumn.STATUS, student_profile.get_status_display()),
            (ReportColumn.STUDENT_ID, student_profile.student_id),

            *zip(self._get_course_headers(meta_courses), self._export_course_grades(student, meta_courses)),
        ]


class ProgressReportForSemester(ProgressReport):
    """
    Input data must contain all student enrollments until target
    semester (inclusive), even without grades.
    Exported data contains club and center courses if target term already passed.
    """

    def __init__(self, term):
        self.target_semester = term
        super().__init__()

    def get_courses_queryset(self, students_queryset):
        return (
            super()
            .get_courses_queryset(students_queryset)
            .filter(semester__index__lte=self.target_semester.index)
        )

    def get_queryset_filters(self):
        return []

    def get_queryset(self):
        enrollments_prefetch = get_enrollments_progress(
            lookup="user__enrollment_set",
            filters=[Q(course__semester__index__lte=self.target_semester.index)],
        )
        return (
            StudentProfile.objects.filter(*self.get_queryset_filters())
            .exclude(status__in=StudentStatuses.inactive_statuses)
            .select_related("user")
            .prefetch_related(enrollments_prefetch)
            .order_by("user__last_name", "user__first_name", "user__pk")
        )

    def process_student(self, student, unique_courses, unique_meta_courses):
        student.enrollments_eq_target_semester = 0
        # During one term student can't enroll on 1 course twice, but for
        # previous terms we should consider this situation and count only
        # unique course ids
        student.success_eq_target_semester = 0
        student.success_lt_target_semester = set()
        # Process enrollments
        super().process_student(student, unique_courses, unique_meta_courses)
        student.success_lt_target_semester = len(student.success_lt_target_semester)

    def before_skip_enrollment(self, enrollment: Enrollment, student, courses):
        """Count stats for enrollments from the passed terms."""
        course = courses[enrollment.course_id]
        grading_system = enrollment.course_program_binding.grading_system
        if course.semester_id == self.target_semester.pk:
            student.enrollments_eq_target_semester += 1
            if enrollment.grade >= grading_system.pass_from:
                student.success_eq_target_semester += 1
        else:
            if enrollment.grade >= grading_system.pass_from:
                student.success_lt_target_semester.add(course.meta_course_id)

    def skip_enrollment(self, enrollment: Enrollment, student, courses):
        """Show enrollments for the target term only."""
        course = courses[enrollment.course_id]
        return course.semester_id != self.target_semester.pk

    def _generate_headers(
        self,
        *,
        meta_courses: dict[int, MetaCourse],
    ) -> list[str]:
        return [
            ReportColumn.ID,
            ReportColumn.FIRST_NAME,
            ReportColumn.LAST_NAME,
            ReportColumn.EMAIL,
            ReportColumn.PHONE,
            ReportColumn.WORKPLACE,
            ReportColumn.GITHUB,
            ReportColumn.UNIVERSITY,
            ReportColumn.YEAR_OF_ADMISSION,
            ReportColumn.PROGRAM_RUN,
            ReportColumn.SEMESTER_NUMBER,
            ReportColumn.STATUS,
            ReportColumn.COMMENT,
            ReportColumn.COMMENT_CHANGED_AT,
            ReportColumn.SUCCESSFUL_ENROLLMENTS_BEFORE.format(semester=self.target_semester),
            ReportColumn.SUCCESSFUL_ENROLLMENTS_IN.format(semester=self.target_semester),
            ReportColumn.ENROLLMENTS_IN.format(semester=self.target_semester),
            *self._get_course_headers(meta_courses),
        ]

    def _export_row(
        self,
        student_profile: StudentProfile,
        *,
        meta_courses: dict[int, MetaCourse],
    ) -> list[tuple[str, str]]:
        student = student_profile.user
        success_total_lt_target_semester = student.success_lt_target_semester
        success_total_eq_target_semester = student.success_eq_target_semester
        enrollments_eq_target_semester = student.enrollments_eq_target_semester
        if student_profile.academic_program_enrollment:
            curriculum_term_index = get_term_index(
                student_profile.academic_program_enrollment.start_year, SemesterTypes.AUTUMN
            )
            term_order = self.target_semester.index - curriculum_term_index + 1
        else:
            term_order = "-"

        return [
            (ReportColumn.ID, student.pk),
            (ReportColumn.FIRST_NAME, student.first_name),
            (ReportColumn.LAST_NAME, student.last_name),
            (ReportColumn.EMAIL, student.email),
            (ReportColumn.PHONE, student.phone),
            (ReportColumn.WORKPLACE, student.workplace),
            (ReportColumn.GITHUB, student.github_login if student.github_login else ""),
            (ReportColumn.UNIVERSITY, student_profile.university),
            (ReportColumn.YEAR_OF_ADMISSION, student_profile.year_of_admission),
            (ReportColumn.PROGRAM_RUN, str(student_profile.academic_program_enrollment) if student_profile.academic_program_enrollment else '-'),
            (ReportColumn.SEMESTER_NUMBER, term_order),
            (ReportColumn.STATUS, student_profile.get_status_display()),
            (ReportColumn.COMMENT, student_profile.comment),
            (ReportColumn.COMMENT_CHANGED_AT, student_profile.get_comment_changed_at_display()),
            (ReportColumn.SUCCESSFUL_ENROLLMENTS_BEFORE.format(semester=self.target_semester), success_total_lt_target_semester),
            (ReportColumn.SUCCESSFUL_ENROLLMENTS_IN.format(semester=self.target_semester), success_total_eq_target_semester),
            (ReportColumn.ENROLLMENTS_IN.format(semester=self.target_semester), enrollments_eq_target_semester),
            *zip(self._get_course_headers(meta_courses), self._export_course_grades(student, meta_courses)),
        ]


class ProgressReportForInvitation(ProgressReportForSemester):
    def __init__(self, invitation):
        self.invitation = invitation
        term = invitation.semester
        super().__init__(term)

    def get_queryset_filters(self):
        student_profiles = Enrollment.objects.filter(invitation=self.invitation).values(
            "student_profile_id"
        )
        return [Q(type=StudentTypes.INVITED), Q(pk__in=student_profiles)]
