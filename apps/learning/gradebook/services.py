import csv
import logging
from decimal import Decimal
from typing import IO, Callable, Dict, List, Optional

from django.core.exceptions import ValidationError, PermissionDenied
from django.utils.translation import gettext_lazy as _

from core.forms import ScoreField
from courses.models import Course
from learning.models import Enrollment, StudentAssignment
from learning.services.enrollment_service import update_enrollment_grade
from learning.services.personal_assignment_service import (
    update_personal_assignment_score
)
from learning.settings import AssignmentScoreUpdateSource, EnrollmentGradeUpdateSource, GradeTypes
from users.models import User

logger = logging.getLogger(__name__)

CSVColumnName = str
CSVColumnValue = str

ID_COLUMN_NAME = 'id'
ASSIGNMENT_SCORE_COLUMN_NAME = 'score'
FINAL_GRADE_COLUMN_NAME = 'final grade'


def assignment_import_scores_from_csv(csv_file: IO,
                                      student_assignments: Dict[CSVColumnValue, StudentAssignment],
                                      changed_by: User,
                                      transform_value: Optional[Callable[[CSVColumnValue], CSVColumnValue]] = None):
    # Remove BOM by using 'utf-8-sig'
    f = (bs.decode("utf-8-sig") for bs in csv_file)
    reader = csv.DictReader(f)
    reader.fieldnames = [name.lower() for name in reader.fieldnames]
    errors = _validate_headers(reader, [ID_COLUMN_NAME, ASSIGNMENT_SCORE_COLUMN_NAME])
    if errors:
        raise ValidationError("<br>".join(errors))

    logger.info(f"Start processing csv")

    found = 0
    imported = 0
    for row_number, row in enumerate(reader, start=1):
        lookup_value = row[ID_COLUMN_NAME].strip()
        if transform_value:
            lookup_value = transform_value(lookup_value)
        if lookup_value not in student_assignments:
            continue
        found += 1
        student_assignment = student_assignments[lookup_value]
        try:
            score_new = _score_to_python(row[ASSIGNMENT_SCORE_COLUMN_NAME])
        except ValidationError as e:
            logger.debug(e.message)
            raise ValidationError(f'Row {row_number}: {e.message}',
                                  code='invalid_score')
            # TODO: collect errors instead?
        try:
            update_personal_assignment_score(student_assignment=student_assignment,
                                             changed_by=changed_by,
                                             score_old=student_assignment.score,
                                             score_new=score_new,
                                             source=AssignmentScoreUpdateSource.CSV_ENROLLMENT)
            logger.info(f"{score_new} points has written to the personal assignment {student_assignment.pk}")
        except ValidationError:
            logger.info(f"Invalid score {score_new} on line {row_number}")
            continue
        imported += 1
    return found, imported


def enrollment_import_grades_from_csv(csv_file: IO,
                                      course: Course,
                                      enrollments: Dict[CSVColumnValue, Enrollment],
                                      changed_by: User,
                                      transform_value: Optional[Callable[[CSVColumnValue], CSVColumnValue]] = None):
    # Remove BOM by using 'utf-8-sig'
    f = (bs.decode("utf-8-sig") for bs in csv_file)
    reader = csv.DictReader(f)
    reader.fieldnames = [name.lower() for name in reader.fieldnames]
    errors = _validate_headers(reader, [ID_COLUMN_NAME, FINAL_GRADE_COLUMN_NAME])
    if errors:
        raise ValidationError("<br>".join(errors))

    logger.info(f"Start processing csv")

    found = 0
    imported = 0
    errors = []
    for row_number, row in enumerate(reader, start=1):
        raw_lookup_value = row[ID_COLUMN_NAME].strip()
        lookup_value = raw_lookup_value
        if transform_value:
            lookup_value = transform_value(raw_lookup_value)
        if lookup_value not in enrollments:
            error_msg = f"Row {row_number}: Student with ID '{raw_lookup_value}' not found."
            logger.warning(error_msg)
            errors.append(error_msg)
            continue
        found += 1
        enrollment = enrollments[lookup_value]
        try:
            final_grade_label = row[FINAL_GRADE_COLUMN_NAME]
            for choice in GradeTypes.get_choices_for_grading_system(
                enrollment.course_program_binding.grading_system_num
            ):
                if choice[1] == final_grade_label:
                    grade = choice[0]
                    break
            else:
                raise ValidationError(f"Grade '{final_grade_label}' doesn't exist or isn't valid for this course's grading system. Student ID '{raw_lookup_value}'.")
        except (KeyError, ValidationError) as e:
            logger.warning(e)
            errors.append(f'Row {row_number}: {e.message if isinstance(e, ValidationError) else e}')
            continue
        try:
            is_success, _ = update_enrollment_grade(enrollment,
                                                    editor=changed_by,
                                                    old_grade=enrollment.grade,
                                                    new_grade=grade,
                                                    source=EnrollmentGradeUpdateSource.CSV_ENROLLMENT)
            if not is_success:
                error_msg = f"Row {row_number}: Update failed due to a conflict with an external change"
                errors.append(error_msg)
                logger.warning(error_msg)
            logger.info(f"Enrollment grade has been updated from {enrollment.grade}"
                        f" to {grade} for {enrollment}")
        except PermissionDenied:
            logger.error(f"You have no permission to change enrollment grade via csv-import.")
            raise
        except ValidationError as ve:
            error_msg = f"Row {row_number}: Invalid grade '{final_grade_label}' for student ID '{raw_lookup_value}' ({ve.message})."
            logger.error(error_msg)
            errors.append(error_msg)
            continue
        except Exception as e:
            logger.error(e)
            errors.append(str(e))
            continue
        imported += 1
    return found, imported, errors


def _validate_headers(reader: csv.DictReader,
                      required_headers: List[CSVColumnName]):
    headers = reader.fieldnames
    errors = []
    for header in required_headers:
        if header not in headers:
            errors.append(_("Header '{}' not found").format(header))
    return errors


_score_field = ScoreField()


def _score_to_python(raw_value: str) -> Optional[Decimal]:
    try:
        cleaned_value = _score_field.clean(raw_value)
    except ValidationError:
        msg = _("Invalid score format '{}'").format(raw_value)
        raise ValidationError(msg, code="invalid_score")
    return cleaned_value
