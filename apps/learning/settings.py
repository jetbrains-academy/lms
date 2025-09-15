from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import TextChoices, Case, When
from django.utils.translation import gettext_lazy as _
from djchoices import C, DjangoChoices, ChoiceItem

# This setting helps calculate the last day of enrollment period if
# a custom value wasn't provided on model saving.
ENROLLMENT_DURATION = getattr(settings, 'ENROLLMENT_DURATION', 45)


# FIXME: move to users?
class AcademicDegreeLevels(DjangoChoices):
    BACHELOR_SPECIALITY_1 = C("1", _('1 course bachelor, speciality'))
    BACHELOR_SPECIALITY_2 = C("2", _('2 course bachelor, speciality'))
    BACHELOR_SPECIALITY_3 = C("3", _('3 course bachelor, speciality'))
    BACHELOR_SPECIALITY_4 = C("4", _('4 course bachelor, speciality'))
    SPECIALITY_5 = C("5", _('5 course speciality'))
    SPECIALITY_6 = C("6_spec", _('6 course speciality'))
    MASTER_1 = C("6", _('1 course magistracy'))
    MASTER_2 = C("7", _('2 course magistracy'))
    POSTGRADUATE = C("8", _('postgraduate'))
    GRADUATE = C("9", _('graduate'))
    OTHER = C("other", _('Other'))


class StudentStatuses(DjangoChoices):
    NORMAL = C('normal', _('Normal'))
    EXPELLED = C('expelled', _('Expelled'))
    GRADUATED = C('graduated', _('Graduated'))

    inactive_statuses = {EXPELLED.value}

    @classmethod
    def is_inactive(cls, status):
        """
        Inactive statuses affect student permissions, e.g. expelled student
        can't enroll in a course
        """
        return status in cls.inactive_statuses


class GradeTypes:
    """
    Used as grade choices for the Enrollment model.
    """

    RE_CREDIT = -1
    NOT_GRADED = 0
    FAIL = 1
    PASS = 3
    GOOD = 4
    EXCELLENT = 5

    _text_choices = [
        (RE_CREDIT, "Re-credit"),
        (NOT_GRADED, "Not graded"),
        (FAIL, "Fail"),
        (PASS, "Pass"),
        (GOOD, "Good"),
        (EXCELLENT, "Excellent"),
    ]
    _text_values = {value: label for value, label in _text_choices}
    choices = _text_choices + [(x, str(x)) for x in range(1, 101)]
    values = {value: label for value, label in choices}

    @classmethod
    def get_choices_for_grading_system(cls, grading_system: int):
        text_values = [GradeTypes.RE_CREDIT, GradeTypes.NOT_GRADED]
        num_values = []
        match grading_system:
            case GradingSystems.BINARY:
                text_values += [GradeTypes.FAIL, GradeTypes.PASS]
            case GradingSystems.BINARY_PLUS_EXCELLENT:
                text_values += [GradeTypes.FAIL, GradeTypes.PASS, GradeTypes.EXCELLENT]
            case GradingSystems.FIVE_POINT:
                num_values = list(range(1, 6))
            case GradingSystems.TEN_POINT:
                num_values = list(range(1, 11))
            case GradingSystems.HUNDRED_POINT:
                num_values = list(range(1, 101))
            case _:
                raise ValidationError(f'Invalid grading system {grading_system}')
        text_choices = [(x, cls._text_values[x]) for x in text_values]
        num_choices = [(x, str(x)) for x in num_values]
        return text_choices + num_choices

    @classmethod
    def get_display_grade(cls, grading_system, grade):
        if (
            grade in (GradeTypes.RE_CREDIT, GradeTypes.NOT_GRADED)
            or grading_system in (GradingSystems.BINARY, GradingSystems.BINARY_PLUS_EXCELLENT)
        ):
            return cls._text_values[grade]
        else:
            return str(grade)


class GradingSystems(DjangoChoices):
    BINARY = C(
        1,
        _("Pass/Fail"),
        pass_from=GradeTypes.PASS,
        good_from=GradeTypes.PASS,
        excellent_from=1000,
    )
    BINARY_PLUS_EXCELLENT = C(
        3,
        _("Pass/Fail + Excellent"),
        pass_from=GradeTypes.PASS,
        good_from=GradeTypes.PASS,
        excellent_from=GradeTypes.EXCELLENT,
    )
    FIVE_POINT = C(
        0,
        _("5-point scale"),
        pass_from=3,
        good_from=4,
        excellent_from=5,
    )
    TEN_POINT = C(
        2,
        _("10-point scale"),
        pass_from=4,
        good_from=7,
        excellent_from=9,
    )
    HUNDRED_POINT = C(
        4,
        _("100-point scale"),
        pass_from=45,
        good_from=70,
        excellent_from=90,
    )

    @classmethod
    def get_passing_grade_expr(cls, path_to_enrollment=''):
        passing_grade_per_system = {key: cls.get_choice(key).pass_from for key in cls.values}
        path_to_grading_system_num = 'course_program_binding__grading_system_num'
        if path_to_enrollment != '':
            path_to_grading_system_num = f'{path_to_enrollment}__{path_to_grading_system_num}'
        return Case(
            *(
                When(**{path_to_grading_system_num: k, 'then': v})
                for k, v in passing_grade_per_system.items()
            )
        )


class EnrollmentGradeUpdateSource(TextChoices):
    GRADEBOOK = 'gradebook', _("Gradebook")
    CSV_ENROLLMENT = 'csv-enrollment', _("Imported from CSV by LMS Student ID")
    FORM_ADMIN = 'admin', _("Admin Panel")


class AssignmentScoreUpdateSource(TextChoices):
    API = 'api', _("REST API")
    CSV_ENROLLMENT = 'csv-enrollment', _("Imported from CSV by LMS Student ID")
    FORM_ADMIN = 'admin', _("Admin Panel")
    FORM_ASSIGNMENT = 'form', _("Form on Assignment Detail Page")
    FORM_GRADEBOOK = 'gradebook', _("Gradebook")
    WEBHOOK_GERRIT = 'webhook-gerrit', _("Gerrit Webhook")
    JBA_SUBMISSION = 'jba-submission', _("JetBrains Academy Submission")
